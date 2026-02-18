from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import websockets
from websockets.asyncio.server import ServerConnection
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from .config import UIServerConfig


class UIServer:
    """Threaded asyncio server for static UI + websocket events."""

    def __init__(
        self,
        config: UIServerConfig,
        logger: Optional[logging.Logger] = None,
    ):
        self._config = config
        self._logger = logger or logging.getLogger("ui_server")
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_async: Optional[asyncio.Event] = None
        self._started = threading.Event()
        self._startup_error: Optional[Exception] = None
        self._connected_clients: set[ServerConnection] = set()
        self._index_html = Path(self._config.index_file).read_bytes()

    @property
    def host(self) -> str:
        return self._config.host

    @property
    def port(self) -> int:
        return self._config.port

    @property
    def websocket_path(self) -> str:
        return self._config.websocket_path

    @property
    def is_running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._startup_error is None
        )

    def start(self, timeout_seconds: float = 5.0) -> None:
        if self.is_running:
            self._logger.warning("UI server is already running")
            return

        self._startup_error = None
        self._started.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="ui-server",
        )
        self._thread.start()

        if not self._started.wait(timeout_seconds):
            raise RuntimeError(
                f"UI server did not start within {timeout_seconds:.1f}s"
            )

        if self._startup_error is not None:
            raise RuntimeError(f"UI server startup failed: {self._startup_error}")

    def stop(self, timeout_seconds: float = 5.0) -> None:
        if self._thread is None:
            return

        if self._loop and self._stop_async:
            self._loop.call_soon_threadsafe(self._stop_async.set)

        self._thread.join(timeout=timeout_seconds)
        if self._thread.is_alive():
            self._logger.error(
                "UI server thread did not stop within %.1fs",
                timeout_seconds,
            )

        self._thread = None
        self._loop = None
        self._stop_async = None

    def publish_state(self, state: str, *, message: Optional[str] = None, **payload) -> None:
        event_payload = {"state": state, **payload}
        if message:
            event_payload["message"] = message
        self.publish("state_update", **event_payload)

    def publish(self, event_type: str, **payload) -> None:
        if not self.is_running or self._loop is None:
            return

        message = json.dumps(
            {
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **payload,
            }
        )

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._broadcast(message),
                self._loop,
            )
            future.add_done_callback(self._consume_future_exception)
        except RuntimeError:
            # Loop may be shutting down.
            return

    @staticmethod
    def _consume_future_exception(future) -> None:
        with contextlib.suppress(Exception):
            future.result()

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_async = asyncio.Event()

        try:
            self._loop.run_until_complete(self._serve())
        except Exception as error:  # pragma: no cover - exercised manually in this phase
            self._startup_error = error
            self._logger.error("UI server failed: %s", error, exc_info=True)
            self._started.set()
        finally:
            if self._loop is not None:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                with contextlib.suppress(Exception):
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self._loop.close()

    async def _serve(self) -> None:
        async with websockets.serve(
            self._handler,
            host=self._config.host,
            port=self._config.port,
            process_request=self._process_request,
            logger=self._logger,
        ):
            self._logger.info(
                "UI server running at http://%s:%d (websocket: %s)",
                self._config.host,
                self._config.port,
                self._config.websocket_path,
            )
            self._started.set()
            await self._stop_async.wait()
            await self._close_clients()

    async def _handler(self, websocket: ServerConnection) -> None:
        request_path = (
            urlsplit(websocket.request.path).path
            if websocket.request is not None
            else ""
        )
        if request_path != self._config.websocket_path:
            await websocket.close(code=1008, reason="Invalid websocket path")
            return

        self._connected_clients.add(websocket)
        self._logger.info("Client connected: %s", websocket.remote_address)
        try:
            await websocket.send(
                self._make_event(
                    "hello",
                    state="idle",
                    message="UI websocket connected",
                )
            )
            async for message in websocket:
                self._logger.debug("Received from UI: %s", message)
        except websockets.exceptions.ConnectionClosed:
            self._logger.info("Client disconnected: %s", websocket.remote_address)
        finally:
            self._connected_clients.discard(websocket)

    async def _process_request(
        self,
        connection: ServerConnection,
        request: Request,
    ) -> Response | None:
        del connection  # Unused in static routing.
        path = urlsplit(request.path).path

        if path == self._config.websocket_path:
            return None

        if path in ("/", "/index.html"):
            return self._response(
                200,
                "OK",
                self._index_html,
                "text/html; charset=utf-8",
            )

        if path == "/healthz":
            return self._response(
                200,
                "OK",
                b"ok\n",
                "text/plain; charset=utf-8",
            )

        return self._response(
            404,
            "Not Found",
            b"not found\n",
            "text/plain; charset=utf-8",
        )

    def _response(
        self,
        status_code: int,
        reason_phrase: str,
        body: bytes,
        content_type: str,
    ) -> Response:
        headers = Headers()
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(len(body))
        headers["Cache-Control"] = "no-store"
        return Response(status_code, reason_phrase, headers, body)

    async def _close_clients(self) -> None:
        if not self._connected_clients:
            return

        tasks = [
            client.close(code=1001, reason="Server shutting down")
            for client in tuple(self._connected_clients)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._connected_clients.clear()

    async def _broadcast(self, message: str) -> None:
        if not self._connected_clients:
            return

        clients = tuple(self._connected_clients)
        disconnected = []
        tasks = [client.send(message) for client in clients]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                disconnected.append(client)
                self._logger.warning("Failed to send message to client: %s", result)

        for client in disconnected:
            self._connected_clients.discard(client)

    @staticmethod
    def _make_event(event_type: str, **payload) -> str:
        return json.dumps(
            {
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **payload,
            }
        )

from __future__ import annotations

import contextlib
import logging
import multiprocessing
import queue
from dataclasses import dataclass
from logging.handlers import QueueHandler
from typing import Callable, Protocol


class WorkerError(RuntimeError):
    """Base class for process worker lifecycle errors."""


class WorkerInitError(WorkerError):
    """Raised when a worker process cannot initialize."""


class WorkerClosedError(WorkerError):
    """Raised when work is submitted after worker shutdown."""


class WorkerCallTimeoutError(WorkerError):
    """Raised when a worker call exceeds its timeout."""


class WorkerCrashError(WorkerError):
    """Raised when a worker process exits unexpectedly."""


class WorkerTaskError(WorkerError):
    """Raised when a worker runtime raises while processing a payload."""


class _WorkerRuntime(Protocol):
    def handle(self, payload: object) -> object:
        ...


WorkerRuntimeFactory = Callable[..., _WorkerRuntime]


@dataclass(frozen=True, slots=True)
class _RequestEnvelope:
    call_id: int
    payload: object


@dataclass(frozen=True, slots=True)
class _ResponseEnvelope:
    kind: str
    call_id: int | None = None
    payload: object | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class _StopSignal:
    pass


_STOP_SIGNAL = _StopSignal()


def _configure_worker_logging(
    *,
    log_queue: multiprocessing.Queue[object] | None,
    log_level: int,
) -> None:
    if log_queue is None:
        return

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    root_logger.setLevel(log_level)
    root_logger.addHandler(QueueHandler(log_queue))


def _set_process_cpu_affinity(
    cpu_cores: tuple[int, ...],
    *,
    logger: logging.Logger,
) -> None:
    if not cpu_cores:
        return

    import os

    cores = sorted(set(cpu_cores))
    core_set = set(cores)

    if hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, core_set)
            logger.info("Pinned process to CPU cores: %s", cores)
            return
        except Exception as error:
            logger.warning("sched_setaffinity failed: %s", error)

    try:
        import psutil  # type: ignore[import-not-found]

        process = psutil.Process()
    except Exception as error:
        logger.warning(
            "CPU affinity requested (%s) but psutil is unavailable: %s",
            cores,
            error,
        )
        return

    cpu_affinity = getattr(process, "cpu_affinity", None)
    if not callable(cpu_affinity):
        logger.warning(
            "CPU affinity requested (%s) but unsupported on this platform.",
            cores,
        )
        return

    try:
        cpu_affinity(cores)
    except Exception as error:
        raise WorkerInitError(
            f"Failed to pin worker to CPU cores {cores}: {error}"
        ) from error

    logger.info("Pinned process to CPU cores: %s", cores)


def _worker_process_loop(
    *,
    name: str,
    runtime_factory: WorkerRuntimeFactory,
    runtime_args: tuple[object, ...],
    cpu_cores: tuple[int, ...],
    log_queue: multiprocessing.Queue[object] | None,
    log_level: int,
    request_queue: multiprocessing.Queue[object],
    response_queue: multiprocessing.Queue[object],
) -> None:
    _configure_worker_logging(log_queue=log_queue, log_level=log_level)
    logger = logging.getLogger(name)
    _set_process_cpu_affinity(cpu_cores, logger=logger)

    try:
        runtime = runtime_factory(*runtime_args)
    except Exception as error:
        response_queue.put(
            _ResponseEnvelope(
                kind="init_error",
                error_type=type(error).__name__,
                error_message=str(error),
            )
        )
        return

    response_queue.put(_ResponseEnvelope(kind="ready"))

    while True:
        message = request_queue.get()
        if isinstance(message, _StopSignal):
            return
        if not isinstance(message, _RequestEnvelope):
            logger.warning("Ignoring unknown worker message type: %s", type(message).__name__)
            continue

        try:
            result = runtime.handle(message.payload)
        except Exception as error:
            response_queue.put(
                _ResponseEnvelope(
                    kind="task_error",
                    call_id=message.call_id,
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
            )
            continue

        response_queue.put(
            _ResponseEnvelope(
                kind="result",
                call_id=message.call_id,
                payload=result,
            )
        )


class _ProcessWorker:
    def __init__(
        self,
        *,
        name: str,
        runtime_factory: WorkerRuntimeFactory,
        runtime_args: tuple[object, ...],
        cpu_cores: tuple[int, ...],
        log_queue: multiprocessing.Queue[object] | None,
        log_level: int,
        logger: logging.Logger,
        startup_timeout_seconds: float = 30.0,
    ):
        self._name = name
        self._runtime_factory = runtime_factory
        self._runtime_args = runtime_args
        self._cpu_cores = tuple(cpu_cores)
        self._log_queue = log_queue
        self._log_level = log_level
        self._logger = logger
        self._startup_timeout_seconds = startup_timeout_seconds
        self._closed = False
        self._call_id = 0
        self._mp_context = multiprocessing.get_context("spawn")
        self._request_queue: multiprocessing.Queue[object] | None = None
        self._response_queue: multiprocessing.Queue[object] | None = None
        self._process: multiprocessing.Process | None = None
        self._start_worker(timeout_seconds=startup_timeout_seconds)

    def _start_worker(self, *, timeout_seconds: float) -> None:
        request_queue: multiprocessing.Queue[object] = self._mp_context.Queue()
        response_queue: multiprocessing.Queue[object] = self._mp_context.Queue()
        process = self._mp_context.Process(
            target=_worker_process_loop,
            kwargs={
                "name": self._name,
                "runtime_factory": self._runtime_factory,
                "runtime_args": self._runtime_args,
                "cpu_cores": self._cpu_cores,
                "log_queue": self._log_queue,
                "log_level": self._log_level,
                "request_queue": request_queue,
                "response_queue": response_queue,
            },
            name=self._name,
        )

        process.start()
        self._request_queue = request_queue
        self._response_queue = response_queue
        self._process = process
        try:
            self._await_ready(timeout_seconds=timeout_seconds)
        except Exception:
            self._shutdown_worker(wait_timeout=0.1)
            raise
        self._logger.info("%s worker ready", self._name)

    def _await_ready(self, *, timeout_seconds: float) -> None:
        try:
            envelope = self._wait_for_response(timeout_seconds=timeout_seconds)
        except WorkerCallTimeoutError as error:
            raise WorkerInitError(f"{self._name} startup timed out.") from error
        except WorkerCrashError as error:
            raise WorkerInitError(f"{self._name} startup failed: {error}") from error
        if envelope.kind == "ready":
            return
        if envelope.kind == "init_error":
            error_type = envelope.error_type or "RuntimeError"
            error_message = envelope.error_message or "unknown error"
            raise WorkerInitError(
                f"{self._name} initialization failed: {error_type}: {error_message}"
            )
        raise WorkerInitError(
            f"{self._name} initialization failed: unexpected response {envelope.kind!r}"
        )

    def _wait_for_response(self, *, timeout_seconds: float) -> _ResponseEnvelope:
        response_queue = self._response_queue
        if response_queue is None:
            raise WorkerCrashError(f"{self._name} response queue is unavailable.")

        try:
            envelope = response_queue.get(timeout=timeout_seconds)
        except queue.Empty as error:
            process = self._process
            if process is not None and process.is_alive():
                raise WorkerCallTimeoutError(f"{self._name} worker timed out.") from error
            raise WorkerCrashError(f"{self._name} worker crashed.") from error
        except Exception as error:
            raise WorkerCrashError(f"{self._name} response channel failed: {error}") from error

        if not isinstance(envelope, _ResponseEnvelope):
            raise WorkerCrashError(
                f"{self._name} worker sent invalid response: {type(envelope).__name__}"
            )
        return envelope

    def _send_request(self, message: object) -> None:
        request_queue = self._request_queue
        if request_queue is None:
            raise WorkerCrashError(f"{self._name} request queue is unavailable.")
        try:
            request_queue.put(message)
        except Exception as error:
            raise WorkerCrashError(f"{self._name} request channel failed: {error}") from error

    def _terminate_process(self, *, wait_timeout: float) -> None:
        process = self._process
        if process is None:
            return

        if process.is_alive():
            process.join(timeout=wait_timeout)
        if process.is_alive():
            with contextlib.suppress(Exception):
                process.terminate()
            process.join(timeout=max(wait_timeout, 0.1))
        if process.is_alive() and hasattr(process, "kill"):
            with contextlib.suppress(Exception):
                process.kill()
            process.join(timeout=max(wait_timeout, 0.1))

        self._process = None

    def _restart_worker(self, *, reason: str) -> None:
        if self._closed:
            raise WorkerClosedError(f"{self._name} worker is closed.")
        self._logger.warning("%s; restarting worker", reason)
        self._shutdown_worker(wait_timeout=0.1)
        try:
            self._start_worker(timeout_seconds=self._startup_timeout_seconds)
        except WorkerError as error:
            self._closed = True
            raise WorkerCrashError(f"{self._name} restart failed: {error}") from error

    def _shutdown_worker(self, *, wait_timeout: float) -> None:
        process = self._process
        if process is None:
            return

        if process.is_alive() and self._request_queue is not None:
            with contextlib.suppress(Exception):
                self._request_queue.put(_STOP_SIGNAL)
        self._terminate_process(wait_timeout=wait_timeout)
        self._request_queue = None
        self._response_queue = None

    def call(self, payload: object, *, timeout_seconds: float = 120.0) -> object:
        if self._closed:
            raise WorkerClosedError(f"{self._name} worker is closed.")

        self._call_id += 1
        call_id = self._call_id
        self._send_request(_RequestEnvelope(call_id=call_id, payload=payload))

        try:
            while True:
                envelope = self._wait_for_response(timeout_seconds=timeout_seconds)
                if envelope.call_id is not None and envelope.call_id != call_id:
                    self._logger.debug(
                        "Ignoring out-of-order %s response for call_id=%s (expected=%s)",
                        self._name,
                        envelope.call_id,
                        call_id,
                    )
                    continue

                if envelope.kind == "result":
                    return envelope.payload
                if envelope.kind == "task_error":
                    error_type = envelope.error_type or "RuntimeError"
                    error_message = envelope.error_message or "unknown error"
                    raise WorkerTaskError(
                        f"{self._name} task failed: {error_type}: {error_message}"
                    )
                if envelope.kind == "init_error":
                    raise WorkerCrashError(
                        f"{self._name} worker re-initialization failed: {envelope.error_message}"
                    )
                raise WorkerCrashError(
                    f"{self._name} worker sent unexpected response: {envelope.kind!r}"
                )
        except WorkerCallTimeoutError as error:
            self._restart_worker(reason=f"{self._name} worker timed out")
            raise WorkerCallTimeoutError(f"{self._name} worker timed out.") from error
        except WorkerCrashError as error:
            self._restart_worker(reason=f"{self._name} worker crashed")
            raise WorkerCrashError(f"{self._name} worker crashed.") from error

    def close(self, timeout_seconds: float = 5.0) -> None:
        if self._closed:
            return
        self._closed = True
        self._shutdown_worker(wait_timeout=max(timeout_seconds, 0.1))

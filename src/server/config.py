from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


class ServerConfigurationError(Exception):
    """Raised when UI server configuration is invalid."""


def _default_index_file() -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base_dir / "web_ui" / "index.html"


@dataclass(frozen=True)
class UIServerConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    websocket_path: str = "/ws"
    index_file: str = ""

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ServerConfigurationError("UI_SERVER_HOST cannot be empty")

        if not 1 <= self.port <= 65535:
            raise ServerConfigurationError(
                f"UI_SERVER_PORT must be in [1, 65535], got: {self.port}"
            )

        if not self.websocket_path.startswith("/"):
            raise ServerConfigurationError(
                f"UI_SERVER_WS_PATH must start with '/', got: {self.websocket_path}"
            )

        if self.enabled:
            if not self.index_file:
                raise ServerConfigurationError("UI_SERVER_INDEX_FILE cannot be empty")

            index_path = Path(self.index_file)
            if not index_path.exists():
                raise ServerConfigurationError(
                    f"UI index file not found: {index_path}"
                )
            if not index_path.is_file():
                raise ServerConfigurationError(
                    f"UI index path is not a file: {index_path}"
                )

    @classmethod
    def from_environment(cls) -> "UIServerConfig":
        enabled = os.getenv("UI_SERVER_ENABLED", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        host = os.getenv("UI_SERVER_HOST", "127.0.0.1").strip()
        port_raw = os.getenv("UI_SERVER_PORT", "8765").strip()
        ws_path = os.getenv("UI_SERVER_WS_PATH", "/ws").strip()
        index_file = os.getenv("UI_SERVER_INDEX_FILE", "").strip()

        try:
            port = int(port_raw)
        except ValueError as error:
            raise ServerConfigurationError(
                f"UI_SERVER_PORT must be an integer, got: {port_raw}"
            ) from error

        if not index_file:
            index_file = str(_default_index_file())

        return cls(
            enabled=enabled,
            host=host,
            port=port,
            websocket_path=ws_path,
            index_file=index_file,
        )

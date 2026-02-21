from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


class ServerConfigurationError(Exception):
    """Raised when UI server configuration is invalid."""


WEBSOCKET_PATH = "/ws"


def _default_index_file() -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base_dir / "web_ui" / "jarvis" / "index.html"


@dataclass(frozen=True)
class UIServerConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    index_file: str = ""

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ServerConfigurationError("UI_SERVER_HOST cannot be empty")

        if not 1 <= self.port <= 65535:
            raise ServerConfigurationError(
                f"UI_SERVER_PORT must be in [1, 65535], got: {self.port}"
            )

        if self.enabled:
            if not self.index_file:
                raise ServerConfigurationError("UI_SERVER_INDEX_FILE cannot be empty")

            index_path = Path(self.index_file)
            if not index_path.exists():
                raise ServerConfigurationError(f"UI index file not found: {index_path}")
            if not index_path.is_file():
                raise ServerConfigurationError(
                    f"UI index path is not a file: {index_path}"
                )

    @property
    def websocket_path(self) -> str:
        return WEBSOCKET_PATH

    @classmethod
    def from_settings(cls, settings) -> "UIServerConfig":
        index_file = settings.index_file.strip() if settings.index_file else ""
        if not index_file:
            index_file = str(_default_index_file())
        return cls(
            enabled=bool(settings.enabled),
            host=settings.host,
            port=settings.port,
            index_file=index_file,
        )

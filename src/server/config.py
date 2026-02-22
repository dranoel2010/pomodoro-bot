"""Configuration model for static UI and websocket server runtime."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


class ServerConfigurationError(Exception):
    """Raised when UI server configuration is invalid."""


WEBSOCKET_PATH = "/ws"
ROOT_PATH = "/"
INDEX_PATH = "/index.html"
HEALTHZ_PATH = "/healthz"
_UI_INDEX_FILES = {
    "jarvis": Path("web_ui") / "jarvis" / "index.html",
    "miro": Path("web_ui") / "miro" / "index.html",
}


def _default_index_file(ui: str) -> Path:
    relative_path = _UI_INDEX_FILES.get(ui)
    if relative_path is None:
        allowed = ", ".join(sorted(_UI_INDEX_FILES))
        raise ServerConfigurationError(f"UI_SERVER_UI must be one of: {allowed}")
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base_dir / relative_path


@dataclass(frozen=True)
class UIServerConfig:
    """Validated UI server configuration derived from app settings."""
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    ui: str = "jarvis"
    index_file: str = ""

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ServerConfigurationError("UI_SERVER_HOST cannot be empty")

        if not 1 <= self.port <= 65535:
            raise ServerConfigurationError(
                f"UI_SERVER_PORT must be in [1, 65535], got: {self.port}"
            )

        if self.ui not in _UI_INDEX_FILES:
            allowed = ", ".join(sorted(_UI_INDEX_FILES))
            raise ServerConfigurationError(f"UI_SERVER_UI must be one of: {allowed}")

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
        raw_ui = getattr(settings, "ui", "jarvis")
        ui = raw_ui.strip().lower() if raw_ui else "jarvis"
        index_file = settings.index_file.strip() if settings.index_file else ""
        if not index_file:
            index_file = str(_default_index_file(ui))
        return cls(
            enabled=bool(settings.enabled),
            host=settings.host,
            port=settings.port,
            ui=ui,
            index_file=index_file,
        )

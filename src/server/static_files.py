"""Safe static-file resolution and content-type helpers for UI assets."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional


def resolve_static_file(ui_root: Path, request_path: str) -> Optional[Path]:
    """Resolve a safe static file path within the configured UI root."""
    root = ui_root.resolve()
    if not request_path or request_path == "/":
        return None

    relative = request_path.lstrip("/")
    if not relative:
        return None

    candidate = (root / relative).resolve()
    if root not in candidate.parents:
        return None

    if not candidate.is_file():
        return None

    return candidate


def guess_content_type(path: Path) -> str:
    """Guess an HTTP content type and append UTF-8 charset for text payloads."""
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        return "application/octet-stream"
    if mime_type.startswith("text/") or mime_type in {
        "application/javascript",
        "application/json",
        "application/xml",
    }:
        return f"{mime_type}; charset=utf-8"
    return mime_type

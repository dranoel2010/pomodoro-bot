"""Shared protocol for resources that support close-based cleanup."""

from __future__ import annotations

from typing import Protocol


class Closeable(Protocol):
    """Minimal interface for process-backed clients that can be closed."""

    def close(self) -> None:
        ...

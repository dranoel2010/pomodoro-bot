"""Shared cross-module contracts and protocol constants."""

from .closeable_protocol import Closeable
from .errors import StartupError

__all__ = ["Closeable", "StartupError"]

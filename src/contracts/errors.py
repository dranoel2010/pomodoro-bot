"""Shared error types used across startup orchestration and factories."""

from __future__ import annotations


class StartupError(Exception):
    """Raised when runtime startup cannot continue."""


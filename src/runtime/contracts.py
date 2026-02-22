"""Protocols describing runtime-facing oracle and config capabilities."""

from __future__ import annotations

import datetime as dt
from typing import Any, Protocol


class OracleSettingsLike(Protocol):
    """Subset of oracle settings required by calendar tool handlers."""
    google_calendar_max_results: int


class AppConfigLike(Protocol):
    """Subset of app configuration required by runtime calendar handlers."""
    oracle: OracleSettingsLike


class CalendarOracleLike(Protocol):
    """Calendar service interface expected by runtime tool dispatch."""
    def list_upcoming_events(
        self,
        *,
        max_results: int,
        time_min: dt.datetime,
    ) -> list[dict[str, Any]]:
        ...

    def add_event(
        self,
        *,
        title: str,
        start: dt.datetime,
        end: dt.datetime,
    ) -> str:
        ...

from __future__ import annotations

import datetime as dt
from typing import Any, Protocol


class OracleSettingsLike(Protocol):
    google_calendar_max_results: int


class AppConfigLike(Protocol):
    oracle: OracleSettingsLike


class CalendarOracleLike(Protocol):
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

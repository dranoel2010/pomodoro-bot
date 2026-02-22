"""Provider protocols and container types used by oracle services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Protocol


class AirQualitySensorLike(Protocol):
    """Protocol for air-quality providers returning normalized readings."""
    def get_readings(self) -> Mapping[str, Any]:
        ...


class LightSensorLike(Protocol):
    """Protocol for light sensors returning normalized readings."""
    def get_readings(self) -> Mapping[str, Any]:
        ...


class CalendarClientLike(Protocol):
    """Protocol for calendar providers used by runtime tool handlers."""
    def get_events(
        self,
        *,
        max_results: int = 10,
        time_min: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        ...

    def add_event(
        self,
        *,
        summary: str,
        start: datetime,
        end: datetime,
    ) -> str:
        ...


@dataclass(frozen=True)
class OracleProviders:
    """Container bundling optional provider instances built at startup."""
    ens160: Optional[AirQualitySensorLike] = None
    temt6000: Optional[LightSensorLike] = None
    calendar: Optional[CalendarClientLike] = None

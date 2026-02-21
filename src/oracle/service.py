from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from .config import OracleConfig
from .contracts import OracleProviders
from .providers import build_oracle_providers


class OracleContextService:
    """Collects environment context from optional oracle providers."""

    def __init__(
        self,
        config: OracleConfig,
        logger: Optional[logging.Logger] = None,
        *,
        providers: Optional[OracleProviders] = None,
        monotonic_fn: Optional[Callable[[], float]] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
    ):
        self._config = config
        self._logger = logger or logging.getLogger("oracle")
        self._monotonic = monotonic_fn or time.monotonic
        self._now = now_fn or (lambda: datetime.now().astimezone())

        self._sensor_cache: Dict[str, Any] = {}
        self._sensor_cache_at: float = 0.0
        self._calendar_cache: Optional[list[dict[str, Any]]] = None
        self._calendar_cache_at: float = 0.0

        provider_bundle = providers or build_oracle_providers(
            self._config,
            logger=self._logger,
        )
        self._ens160 = provider_bundle.ens160
        self._temt6000 = provider_bundle.temt6000
        self._calendar = provider_bundle.calendar

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled

    def build_environment_payload(self) -> Dict[str, Any]:
        """Return fields usable by llm.EnvironmentContext."""
        payload: Dict[str, Any] = {
            "now_local": self._now().isoformat(timespec="seconds"),
        }

        if not self._config.enabled:
            return payload

        sensor_payload = self._read_sensors_with_cache()
        if sensor_payload.get("light_level_lux") is not None:
            payload["light_level_lux"] = sensor_payload["light_level_lux"]
        if sensor_payload.get("air_quality") is not None:
            payload["air_quality"] = sensor_payload["air_quality"]

        upcoming_events = self._read_calendar_with_cache()
        if upcoming_events is not None:
            payload["upcoming_events"] = upcoming_events

        return payload

    def _read_sensors_with_cache(self) -> Dict[str, Any]:
        now = self._monotonic()
        if (
            self._sensor_cache
            and (now - self._sensor_cache_at) < self._config.sensor_cache_ttl_seconds
        ):
            return self._sensor_cache

        result: Dict[str, Any] = {
            "light_level_lux": None,
            "air_quality": None,
        }

        if self._ens160 is not None:
            try:
                result["air_quality"] = dict(self._ens160.get_readings())
            except Exception as error:
                self._logger.warning("Failed to read ENS160 data: %s", error)

        if self._temt6000 is not None:
            try:
                readings = dict(self._temt6000.get_readings())
                result["light_level_lux"] = readings.get("illuminance_lux")
            except Exception as error:
                self._logger.warning("Failed to read TEMT6000 data: %s", error)

        self._sensor_cache = result
        self._sensor_cache_at = now
        return result

    def _read_calendar_with_cache(self) -> Optional[list[dict[str, Any]]]:
        if self._calendar is None:
            return None

        now = self._monotonic()
        if (
            self._calendar_cache is not None
            and (now - self._calendar_cache_at)
            < self._config.calendar_cache_ttl_seconds
        ):
            return self._calendar_cache

        try:
            events = self._calendar.get_events(
                max_results=self._config.calendar_max_results
            )
            self._calendar_cache = events
            self._calendar_cache_at = now
            return events
        except Exception as error:
            self._logger.warning("Failed to read Google Calendar data: %s", error)
            return self._calendar_cache

    def list_upcoming_events(
        self,
        *,
        max_results: Optional[int] = None,
        time_min: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        if self._calendar is None:
            raise RuntimeError("Google Calendar integration is not available.")

        limit = (
            int(max_results)
            if isinstance(max_results, int) and max_results > 0
            else self._config.calendar_max_results
        )
        return self._calendar.get_events(max_results=limit, time_min=time_min)

    def add_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
    ) -> str:
        if self._calendar is None:
            raise RuntimeError("Google Calendar integration is not available.")
        return self._calendar.add_event(summary=title, start=start, end=end)

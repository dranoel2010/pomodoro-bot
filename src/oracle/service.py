"""Context aggregation service with TTL caching for sensors and calendar."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable

from contracts.oracle import OracleProviders

from .config import OracleConfig
from .providers import build_oracle_providers


class OracleContextService:
    """Collects environment context from optional oracle providers."""

    def __init__(
        self,
        config: OracleConfig,
        logger: logging.Logger | None = None,
        *,
        providers: OracleProviders | None = None,
        monotonic_fn: Callable[[], float] | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ):
        self._config = config
        self._logger = logger or logging.getLogger("oracle")
        self._monotonic = monotonic_fn or time.monotonic
        self._now = now_fn or (lambda: datetime.now().astimezone())

        self._sensor_cache: dict[str, object] = {}
        self._sensor_cache_at: float = 0.0
        self._calendar_cache: list[dict[str, object]] | None = None
        self._calendar_cache_at: float = 0.0

        provider_bundle = providers or build_oracle_providers(
            self._config,
            logger=self._logger,
        )
        self._ens160 = provider_bundle.ens160
        self._temt6000 = provider_bundle.temt6000
        self._calendar = provider_bundle.calendar

    def build_environment_payload(self) -> dict[str, object]:
        """Return fields usable by llm.EnvironmentContext."""
        payload: dict[str, object] = {
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

    def _read_sensors_with_cache(self) -> dict[str, object]:
        now = self._monotonic()
        if (
            self._sensor_cache
            and (now - self._sensor_cache_at) < self._config.sensor_cache_ttl_seconds
        ):
            return self._sensor_cache

        result: dict[str, object] = {
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

    def _read_calendar_with_cache(self) -> list[dict[str, object]] | None:
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
        max_results: int | None = None,
        time_min: datetime | None = None,
    ) -> list[dict[str, object]]:
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

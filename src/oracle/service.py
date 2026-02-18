from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from .calendar import GoogleCalendar
from .config import OracleConfig
from .sensor import ENS160Sensor, TEMT6000Sensor


class OracleContextService:
    """Collects environment context from optional oracle providers."""

    def __init__(self, config: OracleConfig, logger: Optional[logging.Logger] = None):
        self._config = config
        self._logger = logger or logging.getLogger("oracle")
        self._ens160: Optional[ENS160Sensor] = None
        self._temt6000: Optional[TEMT6000Sensor] = None
        self._calendar: Optional[GoogleCalendar] = None

        self._sensor_cache: Dict[str, Any] = {}
        self._sensor_cache_at: float = 0.0
        self._calendar_cache: Optional[list[dict[str, Any]]] = None
        self._calendar_cache_at: float = 0.0

        self._initialize_providers()

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled

    def _initialize_providers(self) -> None:
        if not self._config.enabled:
            self._logger.info("Oracle integrations disabled (ORACLE_ENABLED=false)")
            return

        if self._config.ens160_enabled:
            try:
                self._ens160 = ENS160Sensor(
                    temperature_compensation_c=self._config.ens160_temperature_compensation_c,
                    humidity_compensation_pct=self._config.ens160_humidity_compensation_pct,
                    logger=self._logger.getChild("ens160"),
                )
                self._logger.info("ENS160 sensor enabled")
            except Exception as error:
                self._logger.warning("ENS160 unavailable: %s", error)

        if self._config.temt6000_enabled:
            try:
                self._temt6000 = TEMT6000Sensor(
                    channel=self._config.temt6000_channel,
                    gain=self._config.temt6000_gain,
                    adc_address=self._config.temt6000_adc_address,
                    busnum=self._config.temt6000_busnum,
                    logger=self._logger.getChild("temt6000"),
                )
                self._logger.info("TEMT6000 sensor enabled")
            except Exception as error:
                self._logger.warning("TEMT6000 unavailable: %s", error)

        if self._config.calendar_enabled:
            if (
                not self._config.calendar_id
                or not self._config.calendar_service_account_file
            ):
                self._logger.warning(
                    "Calendar integration enabled but ORACLE_GOOGLE_CALENDAR_ID or "
                    "ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE is missing."
                )
            else:
                try:
                    self._calendar = GoogleCalendar(
                        calendar_id=self._config.calendar_id,
                        service_account_file=self._config.calendar_service_account_file,
                        read_only=True,
                        logger=self._logger.getChild("calendar"),
                    )
                    self._logger.info("Google Calendar integration enabled")
                except Exception as error:
                    self._logger.warning("Google Calendar unavailable: %s", error)

    def build_environment_payload(self) -> Dict[str, Any]:
        """Return fields usable by llm.EnvironmentContext."""
        payload: Dict[str, Any] = {
            "now_local": datetime.now().astimezone().isoformat(timespec="seconds"),
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
        now = time.monotonic()
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

        now = time.monotonic()
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

    @classmethod
    def from_environment(
        cls,
        logger: Optional[logging.Logger] = None,
    ) -> "OracleContextService":
        config = OracleConfig.from_environment()
        return cls(config=config, logger=logger)

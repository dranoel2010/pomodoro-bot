from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    text = raw.strip().lower()
    base = 16 if text.startswith("0x") else 10
    return int(text, base)


@dataclass(frozen=True)
class OracleConfig:
    enabled: bool
    ens160_enabled: bool
    temt6000_enabled: bool
    calendar_enabled: bool

    ens160_temperature_compensation_c: float
    ens160_humidity_compensation_pct: float

    temt6000_channel: int
    temt6000_gain: int
    temt6000_adc_address: int
    temt6000_busnum: int

    calendar_id: str
    calendar_service_account_file: str
    calendar_max_results: int

    sensor_cache_ttl_seconds: float
    calendar_cache_ttl_seconds: float

    def __post_init__(self) -> None:
        if self.temt6000_channel not in (0, 1, 2, 3):
            raise ValueError(
                f"ORACLE_TEMT6000_CHANNEL must be 0..3, got: {self.temt6000_channel}"
            )
        if self.calendar_max_results < 1:
            raise ValueError(
                f"ORACLE_GOOGLE_CALENDAR_MAX_RESULTS must be >= 1, got: {self.calendar_max_results}"
            )
        if self.sensor_cache_ttl_seconds < 0:
            raise ValueError("ORACLE_SENSOR_CACHE_TTL_SECONDS must be >= 0")
        if self.calendar_cache_ttl_seconds < 0:
            raise ValueError("ORACLE_CALENDAR_CACHE_TTL_SECONDS must be >= 0")

    @classmethod
    def from_settings(
        cls,
        settings,
        *,
        calendar_id: str | None = None,
        calendar_service_account_file: str | None = None,
    ) -> "OracleConfig":
        return cls(
            enabled=bool(settings.enabled),
            ens160_enabled=bool(settings.ens160_enabled),
            temt6000_enabled=bool(settings.temt6000_enabled),
            calendar_enabled=bool(settings.google_calendar_enabled),
            ens160_temperature_compensation_c=float(
                settings.ens160_temperature_compensation_c
            ),
            ens160_humidity_compensation_pct=float(
                settings.ens160_humidity_compensation_pct
            ),
            temt6000_channel=int(settings.temt6000_channel),
            temt6000_gain=int(settings.temt6000_gain),
            temt6000_adc_address=int(settings.temt6000_adc_address),
            temt6000_busnum=int(settings.temt6000_busnum),
            calendar_id=(calendar_id or "").strip(),
            calendar_service_account_file=(calendar_service_account_file or "").strip(),
            calendar_max_results=int(settings.google_calendar_max_results),
            sensor_cache_ttl_seconds=float(settings.sensor_cache_ttl_seconds),
            calendar_cache_ttl_seconds=float(settings.calendar_cache_ttl_seconds),
        )

    @classmethod
    def from_environment(cls) -> "OracleConfig":
        calendar_id = os.getenv("ORACLE_GOOGLE_CALENDAR_ID", "").strip()
        service_account_file = os.getenv(
            "ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE",
            "",
        ).strip()
        calendar_default_enabled = bool(calendar_id and service_account_file)

        return cls(
            enabled=_bool("ORACLE_ENABLED", True),
            ens160_enabled=_bool("ORACLE_ENS160_ENABLED", False),
            temt6000_enabled=_bool("ORACLE_TEMT6000_ENABLED", False),
            calendar_enabled=_bool(
                "ORACLE_GOOGLE_CALENDAR_ENABLED",
                calendar_default_enabled,
            ),
            ens160_temperature_compensation_c=_float(
                "ORACLE_ENS160_TEMPERATURE_COMPENSATION_C",
                25.0,
            ),
            ens160_humidity_compensation_pct=_float(
                "ORACLE_ENS160_HUMIDITY_COMPENSATION_PCT",
                50.0,
            ),
            temt6000_channel=_int("ORACLE_TEMT6000_CHANNEL", 0),
            temt6000_gain=_int("ORACLE_TEMT6000_GAIN", 1),
            temt6000_adc_address=_int("ORACLE_TEMT6000_ADC_ADDRESS", 0x48),
            temt6000_busnum=_int("ORACLE_TEMT6000_BUSNUM", 1),
            calendar_id=calendar_id,
            calendar_service_account_file=service_account_file,
            calendar_max_results=_int("ORACLE_GOOGLE_CALENDAR_MAX_RESULTS", 5),
            sensor_cache_ttl_seconds=_float("ORACLE_SENSOR_CACHE_TTL_SECONDS", 15.0),
            calendar_cache_ttl_seconds=_float(
                "ORACLE_CALENDAR_CACHE_TTL_SECONDS",
                60.0,
            ),
        )

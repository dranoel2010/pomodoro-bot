"""Typed configuration model for optional oracle integrations."""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class OracleConfig:
    """Validated oracle runtime configuration assembled from app settings and secrets."""
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

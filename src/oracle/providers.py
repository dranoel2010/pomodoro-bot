"""Factory for building available oracle providers from configuration."""

from __future__ import annotations

import logging

from .calendar import GoogleCalendar
from .config import OracleConfig
from .contracts import OracleProviders
from .sensor import ENS160Sensor, TEMT6000Sensor


def build_oracle_providers(
    config: OracleConfig,
    *,
    logger: logging.Logger,
) -> OracleProviders:
    """Initialize configured oracle providers and degrade gracefully on failures."""
    if not config.enabled:
        logger.info("Oracle integrations disabled (ORACLE_ENABLED=false)")
        return OracleProviders()

    ens160 = None
    temt6000 = None
    calendar = None

    if config.ens160_enabled:
        try:
            ens160 = ENS160Sensor(
                temperature_compensation_c=config.ens160_temperature_compensation_c,
                humidity_compensation_pct=config.ens160_humidity_compensation_pct,
                logger=logger.getChild("ens160"),
            )
            logger.info("ENS160 sensor enabled")
        except Exception as error:
            logger.warning("ENS160 unavailable: %s", error)

    if config.temt6000_enabled:
        try:
            temt6000 = TEMT6000Sensor(
                channel=config.temt6000_channel,
                gain=config.temt6000_gain,
                adc_address=config.temt6000_adc_address,
                busnum=config.temt6000_busnum,
                logger=logger.getChild("temt6000"),
            )
            logger.info("TEMT6000 sensor enabled")
        except Exception as error:
            logger.warning("TEMT6000 unavailable: %s", error)

    if config.calendar_enabled:
        if not config.calendar_id or not config.calendar_service_account_file:
            logger.warning(
                "Calendar integration enabled but ORACLE_GOOGLE_CALENDAR_ID or "
                "ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE is missing."
            )
        else:
            try:
                calendar = GoogleCalendar(
                    calendar_id=config.calendar_id,
                    service_account_file=config.calendar_service_account_file,
                    read_only=False,
                    logger=logger.getChild("calendar"),
                )
                logger.info("Google Calendar integration enabled")
            except Exception as error:
                logger.warning("Google Calendar unavailable: %s", error)

    return OracleProviders(
        ens160=ens160,
        temt6000=temt6000,
        calendar=calendar,
    )

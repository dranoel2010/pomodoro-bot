"""Startup factory for optional oracle context service construction."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .config import OracleConfig
from .service import OracleContextService

if TYPE_CHECKING:
    from app_config import OracleSettings


def create_oracle_service(
    *,
    oracle: "OracleSettings",
    calendar_id: str | None,
    service_account_file: str | None,
    logger: logging.Logger,
) -> OracleContextService | None:
    """Build oracle context service, degrading gracefully on startup failures."""

    try:
        oracle_config = OracleConfig.from_settings(
            oracle,
            calendar_id=calendar_id,
            calendar_service_account_file=service_account_file,
        )
        return OracleContextService(
            config=oracle_config,
            logger=logging.getLogger("oracle"),
        )
    except Exception as error:
        logger.warning(
            "Oracle context unavailable (%s: %s); continuing startup without it.",
            type(error).__name__,
            error,
        )
        logger.debug("Oracle context initialization traceback", exc_info=True)
        return None

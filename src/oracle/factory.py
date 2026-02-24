from __future__ import annotations

import logging

from .config import OracleConfig
from .service import OracleContextService


def create_oracle_service(*, oracle, calendar_id: str | None, service_account_file: str | None, logger: logging.Logger) -> OracleContextService | None:
    try:
        return OracleContextService(
            config=OracleConfig.from_settings(
                oracle,
                calendar_id=calendar_id,
                calendar_service_account_file=service_account_file,
            ),
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

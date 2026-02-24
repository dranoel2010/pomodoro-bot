"""Startup factory for optional UI server construction."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from contracts.ui_protocol import STATE_IDLE

from .config import UIServerConfig
from .service import UIServer

if TYPE_CHECKING:
    from app_config import UIServerSettings


def create_ui_server(
    *,
    ui: "UIServerSettings",
    logger: logging.Logger,
) -> UIServer | None:
    """Build and start the optional UI server, degrading on startup errors."""

    try:
        ui_server_config = UIServerConfig.from_settings(ui)
        if not ui_server_config.enabled:
            return None

        ui_server = UIServer(
            config=ui_server_config,
            logger=logging.getLogger("ui_server"),
        )
        logger.info("Starting UI server...")
        ui_server.start(timeout_seconds=5.0)
        logger.info(
            "UI server ready at http://%s:%d",
            ui_server.host,
            ui_server.port,
        )
        ui_server.publish_state(STATE_IDLE, message="UI server connected")
        return ui_server
    except Exception as error:
        logger.warning(
            "UI server unavailable (%s: %s); continuing startup without it.",
            type(error).__name__,
            error,
        )
        logger.debug("UI server initialization traceback", exc_info=True)
        return None

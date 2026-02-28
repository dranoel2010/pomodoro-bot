from __future__ import annotations

import logging

from contracts import StartupError
from contracts.ui_protocol import STATE_IDLE

from .config import ServerConfigurationError, UIServerConfig
from .service import UIServer


def create_ui_server(*, ui, logger: logging.Logger) -> UIServer | None:
    try:
        ui_server_config = UIServerConfig.from_settings(ui)
        if not ui_server_config.enabled:
            return None

        ui_server = UIServer(config=ui_server_config, logger=logging.getLogger("ui_server"))
        logger.info("Starting UI server...")
        ui_server.start(timeout_seconds=5.0)
        logger.info("UI server ready at http://%s:%d", ui_server.host, ui_server.port)
        ui_server.publish_state(STATE_IDLE, message="UI server connected")
        return ui_server
    except (ServerConfigurationError, OSError, RuntimeError) as error:
        logger.warning(
            "UI server unavailable (%s: %s); continuing startup without it.",
            type(error).__name__,
            error,
        )
        logger.debug("UI server initialization traceback", exc_info=True)
        return None
    except Exception as error:
        raise StartupError(
            f"UI server initialization failed: {type(error).__name__}: {error}"
        ) from error

"""Standalone launcher for the UI server."""

import logging
import signal
import sys
import time
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_config import AppConfigurationError, load_app_config, resolve_config_path
from server import ServerConfigurationError, UIServer, UIServerConfig


def main() -> int:
    """Run the standalone UI server process until interrupted."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("ui_server")

    try:
        app_config = load_app_config(str(resolve_config_path()))
        config = UIServerConfig.from_settings(app_config.ui_server)
    except (AppConfigurationError, ServerConfigurationError) as error:
        logger.error("UI server configuration error: %s", error)
        return 1

    if not config.enabled:
        logger.info("UI server disabled via UI_SERVER_ENABLED=false")
        return 0

    server = UIServer(config=config, logger=logger)

    try:
        server.start()
        logger.info("Press Ctrl+C to stop.")

        shutdown = False

        def handle_signal(signum, frame) -> None:
            del frame
            nonlocal shutdown
            logger.info("Signal %s received, stopping.", signal.Signals(signum).name)
            shutdown = True

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        while not shutdown:
            time.sleep(0.2)

    except KeyboardInterrupt:
        logger.info("Stopping by user request.")
    finally:
        server.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

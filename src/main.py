from __future__ import annotations

import logging
import multiprocessing
import signal
import sys
import time
from logging.handlers import QueueListener
from multiprocessing.queues import Queue as MPQueue
from types import FrameType
from typing import TYPE_CHECKING

from app_config import (
    AppConfig,
    AppConfigurationError,
    SecretConfig,
    load_app_config,
    load_secret_config,
    resolve_config_path,
)
from contracts import StartupError
from oracle.factory import create_oracle_service
from server.factory import create_ui_server

if TYPE_CHECKING:
    from stt.service import WakeWordService

LogQueue = MPQueue


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(processName)s:%(process)d] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    return logging.getLogger("wake_word_app")


def setup_signal_handlers(service: WakeWordService) -> None:
    logger = logging.getLogger("wake_word_app")

    def signal_handler(signum: int, frame: FrameType | None) -> None:
        del frame
        signal_name = signal.Signals(signum).name
        logger.info("%s received, stopping...", signal_name)
        try:
            service.stop()
        except Exception as error:  # pragma: no cover - only on abnormal shutdown
            logger.error("Error while stopping service on %s: %s", signal_name, error)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def _wait_for_service_ready_callback(service: WakeWordService, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    poll_interval_seconds = 0.25

    while time.monotonic() < deadline:
        if not service.is_running:
            return False

        remaining = deadline - time.monotonic()
        wait_seconds = min(poll_interval_seconds, max(remaining, 0.0))
        if service.wait_until_ready(timeout=wait_seconds):
            return True

    return bool(service.is_ready)


def _load_runtime_config(logger: logging.Logger) -> tuple[AppConfig, SecretConfig]:
    try:
        config_path = resolve_config_path()
        app_config = load_app_config(str(config_path))
        secret_config = load_secret_config()
    except AppConfigurationError as error:
        raise StartupError(f"App configuration error: {error}")

    logger.info("Loaded runtime config: %s", config_path)
    return app_config, secret_config


def _start_log_listener() -> tuple[LogQueue, QueueListener]:
    spawn_context = multiprocessing.get_context("spawn")
    log_queue: MPQueue = spawn_context.Queue()
    handlers = list(logging.getLogger().handlers)
    listener = QueueListener(log_queue, *handlers, respect_handler_level=True)
    listener.start()
    return log_queue, listener


def _load_runtime_engine():
    try:
        from runtime import RuntimeEngine
    except ImportError as error:
        raise StartupError(f"Runtime loop import error: {error}")
    return RuntimeEngine


def _load_worker_factories():
    try:
        from runtime.workers import (
            create_llm_worker,
            create_stt_worker,
            create_tts_worker,
        )
    except ImportError as error:
        raise StartupError(f"Runtime worker import error: {error}")
    return create_stt_worker, create_llm_worker, create_tts_worker


def _safe_close(resource: object | None, *, label: str, logger: logging.Logger) -> None:
    if resource is None:
        return
    close_method = getattr(resource, "close", None)
    if not callable(close_method):
        return
    try:
        close_method()
    except Exception as error:
        logger.error("Failed to close %s: %s", label, error)


def main() -> int:
    logger = setup_logging(level=logging.INFO)
    stt_client = None
    speech_service = None
    assistant_llm = None
    log_listener: QueueListener | None = None

    try:
        log_queue, log_listener = _start_log_listener()
        app_config, secret_config = _load_runtime_config(logger)
        log_level = logging.getLogger().getEffectiveLevel()
        create_stt_worker, create_llm_worker, create_tts_worker = _load_worker_factories()

        wake_word_config, stt_client = create_stt_worker(
            wake_word=app_config.wake_word,
            stt=app_config.stt,
            pico_key=secret_config.pico_voice_access_key,
            log_queue=log_queue,
            log_level=log_level,
        )
        speech_service = create_tts_worker(
            tts=app_config.tts,
            log_queue=log_queue,
            log_level=log_level,
        )
        assistant_llm = create_llm_worker(
            llm=app_config.llm,
            hf_token=secret_config.hf_token,
            log_queue=log_queue,
            log_level=log_level,
            logger=logger,
        )
        if assistant_llm is None and speech_service is not None:
            logger.warning(
                "TTS is enabled but LLM is disabled; no spoken reply will be generated."
            )

        oracle_service = None
        if assistant_llm is not None:
            oracle_service = create_oracle_service(
                oracle=app_config.oracle,
                calendar_id=secret_config.oracle_google_calendar_id,
                service_account_file=secret_config.oracle_google_service_account_file,
                logger=logger,
            )

        ui_server = create_ui_server(ui=app_config.ui_server, logger=logger)

        return _load_runtime_engine()(
            logger=logger,
            app_config=app_config,
            wake_word_config=wake_word_config,
            stt=stt_client,
            assistant_llm=assistant_llm,
            speech_service=speech_service,
            oracle_service=oracle_service,
            ui_server=ui_server,
            setup_signal_handlers=setup_signal_handlers,
            wait_for_service_ready=_wait_for_service_ready_callback,
        ).run()
    except StartupError as error:
        logger.error("%s", error)
        return 1
    except Exception:
        logger.exception("Unhandled startup failure")
        return 1
    finally:
        _safe_close(assistant_llm, label="LLM process client", logger=logger)
        _safe_close(speech_service, label="TTS process client", logger=logger)
        _safe_close(stt_client, label="STT process client", logger=logger)
        if log_listener is not None:
            log_listener.stop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

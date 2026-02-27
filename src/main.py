from __future__ import annotations

from contextlib import ExitStack
from functools import partial
import logging
import multiprocessing
import signal
import sys
import time
from logging.handlers import QueueListener
from multiprocessing.queues import Queue as MPQueue
from types import FrameType
from typing import Callable

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
from llm.config import ConfigurationError as LLMConfigurationError
from llm.config import LLMConfig
from runtime.ports import WakeWordServicePort
from runtime.process_workers import ProcessLLMClient, ProcessSTTClient, ProcessTTSClient
from stt.config import ConfigurationError as STTConfigurationError
from stt.config import STTConfig, WakeWordConfig
from tts.config import TTSConfig, TTSConfigurationError

LogQueue = MPQueue[object]


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(processName)s:%(process)d] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    return logging.getLogger("wake_word_app")


def setup_signal_handlers(service: WakeWordServicePort) -> None:
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


def _wait_for_service_ready_callback(
    service: WakeWordServicePort,
    timeout: float = 10.0,
) -> bool:
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
        from runtime import PipecatRuntimeEngine
    except ImportError as error:
        raise StartupError(f"Runtime loop import error: {error}")
    return PipecatRuntimeEngine


def _close_with_log(
    name: str,
    close_fn: Callable[[], None],
    logger: logging.Logger,
) -> None:
    try:
        close_fn()
    except Exception as error:
        logger.error("Failed to close %s: %s", name, error)


def main() -> int:
    logger = setup_logging(level=logging.INFO)
    with ExitStack() as cleanup:
        try:
            log_queue, log_listener = _start_log_listener()
            cleanup.callback(
                _close_with_log,
                "log listener",
                log_listener.stop,
                logger,
            )

            app_config, secret_config = _load_runtime_config(logger)
            log_level = logging.getLogger().getEffectiveLevel()

            wake_settings = app_config.pipecat.wake.porcupine
            stt_settings = app_config.pipecat.stt.faster_whisper
            llm_settings = app_config.pipecat.llm.local_llama
            tts_settings = app_config.pipecat.tts.piper
            calendar_settings = app_config.pipecat.tools.calendar
            ui_settings = app_config.pipecat.ui

            wake_word_config = WakeWordConfig.from_settings(
                pico_voice_access_key=secret_config.pico_voice_access_key,
                settings=wake_settings,
            )
            stt_client = ProcessSTTClient(
                config=STTConfig.from_settings(stt_settings),
                cpu_cores=stt_settings.cpu_cores,
                logger=logging.getLogger("stt.process"),
                log_queue=log_queue,
                log_level=log_level,
            )
            cleanup.callback(
                _close_with_log,
                "STT process client",
                partial(stt_client.close, timeout_seconds=5.0),
                logger,
            )

            speech_service = None
            if tts_settings.enabled:
                speech_service = ProcessTTSClient(
                    config=TTSConfig.from_settings(tts_settings),
                    cpu_cores=tts_settings.cpu_cores,
                    logger=logging.getLogger("tts.process"),
                    log_queue=log_queue,
                    log_level=log_level,
                )
                cleanup.callback(
                    _close_with_log,
                    "TTS process client",
                    partial(speech_service.close, timeout_seconds=5.0),
                    logger,
                )

            assistant_llm = None
            if llm_settings.enabled:
                llm_config = LLMConfig.from_sources(
                    model_dir=llm_settings.model_path,
                    hf_filename=llm_settings.hf_filename,
                    hf_repo_id=llm_settings.hf_repo_id or None,
                    hf_revision=llm_settings.hf_revision or None,
                    hf_token=secret_config.hf_token,
                    system_prompt_path=llm_settings.system_prompt or None,
                    max_tokens=llm_settings.max_tokens,
                    n_threads=llm_settings.n_threads,
                    n_threads_batch=llm_settings.n_threads_batch,
                    n_ctx=llm_settings.n_ctx,
                    n_batch=llm_settings.n_batch,
                    n_ubatch=llm_settings.n_ubatch,
                    temperature=llm_settings.temperature,
                    top_p=llm_settings.top_p,
                    top_k=llm_settings.top_k,
                    min_p=llm_settings.min_p,
                    repeat_penalty=llm_settings.repeat_penalty,
                    use_mmap=llm_settings.use_mmap,
                    use_mlock=llm_settings.use_mlock,
                    verbose=llm_settings.verbose,
                    logger=logging.getLogger("llm.config"),
                )
                assistant_llm = ProcessLLMClient(
                    config=llm_config,
                    cpu_cores=llm_settings.cpu_cores,
                    cpu_affinity_mode=llm_settings.cpu_affinity_mode,
                    shared_cpu_reserve_cores=llm_settings.shared_cpu_reserve_cores,
                    logger=logging.getLogger("llm.process"),
                    log_queue=log_queue,
                    log_level=log_level,
                )
                cleanup.callback(
                    _close_with_log,
                    "LLM process client",
                    partial(assistant_llm.close, timeout_seconds=5.0),
                    logger,
                )
                logger.info("LLM enabled (model: %s)", llm_config.model_path)

            if assistant_llm is None and speech_service is not None:
                logger.warning(
                    "TTS is enabled but LLM is disabled; no spoken reply will be generated."
                )

            oracle_service = None
            if assistant_llm is not None:
                oracle_service = create_oracle_service(
                    oracle=calendar_settings,
                    calendar_id=secret_config.oracle_google_calendar_id,
                    service_account_file=secret_config.oracle_google_service_account_file,
                    logger=logger,
                )

            ui_server = create_ui_server(ui=ui_settings, logger=logger)
            if ui_server is not None:
                cleanup.callback(
                    _close_with_log,
                    "UI server",
                    partial(ui_server.stop, timeout_seconds=5.0),
                    logger,
                )

            runtime_engine = _load_runtime_engine()(
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
            )
            return runtime_engine.run()
        except (
            STTConfigurationError,
            LLMConfigurationError,
            TTSConfigurationError,
        ) as error:
            logger.error("Runtime configuration error: %s", error)
            return 1
        except StartupError as error:
            logger.error("%s", error)
            return 1
        except Exception:
            logger.exception("Unhandled startup failure")
            return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

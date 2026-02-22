"""Application entrypoint that bootstraps services and runs the runtime loop."""

from __future__ import annotations

import logging
import multiprocessing
import signal
import sys
import time
from typing import Any, Optional

from contracts.ui_protocol import STATE_IDLE

class StartupError(Exception):
    """Raised when runtime startup cannot continue."""


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure logging for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("wake_word_app")


def setup_signal_handlers(service: Any) -> None:
    """Set up graceful shutdown on SIGTERM and SIGINT."""
    logger = logging.getLogger("wake_word_app")

    def signal_handler(signum: int, frame: Any) -> None:
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


def wait_for_service_ready(service: Any, timeout: float = 10.0) -> bool:
    """Wait for service to become ready, with fast-fail on crash."""
    start_time = time.time()
    poll_interval = 0.1

    while time.time() - start_time < timeout:
        if service.is_ready:
            return True

        if not service.is_running:
            return False

        time.sleep(poll_interval)

    return service.is_ready


def _load_runtime_config(logger: logging.Logger) -> tuple[Any, Any]:
    from app_config import (
        AppConfigurationError,
        load_app_config,
        load_secret_config,
        resolve_config_path,
    )

    try:
        config_path = resolve_config_path()
        app_config = load_app_config(str(config_path))
        secret_config = load_secret_config()
    except AppConfigurationError as error:
        raise StartupError(f"App configuration error: {error}") from error

    logger.info("Loaded runtime config: %s", config_path)
    return app_config, secret_config


def _initialize_stt(
    *,
    app_config: Any,
    secret_config: Any,
) -> tuple[Any, Any]:
    try:
        from stt import (
            ConfigurationError,
            FasterWhisperSTT,
            STTConfig,
            STTError,
            WakeWordConfig,
        )
    except Exception as error:
        raise StartupError(f"STT module import error: {error}") from error

    try:
        wake_word_config = WakeWordConfig.from_settings(
            pico_voice_access_key=secret_config.pico_voice_access_key,
            settings=app_config.wake_word,
        )
        stt_config = STTConfig.from_settings(app_config.stt)
    except ConfigurationError as error:
        raise StartupError(f"Configuration error: {error}") from error

    try:
        stt = FasterWhisperSTT(
            model_size=stt_config.model_size,
            device=stt_config.device,
            compute_type=stt_config.compute_type,
            language=stt_config.language,
            beam_size=stt_config.beam_size,
            vad_filter=stt_config.vad_filter,
            logger=logging.getLogger("stt"),
        )
    except STTError as error:
        raise StartupError(f"STT initialization error: {error}") from error

    return wake_word_config, stt


def _initialize_tts(
    *,
    app_config: Any,
    logger: logging.Logger,
) -> Optional[Any]:
    if not app_config.tts.enabled:
        return None

    try:
        from tts import (
            PiperTTSEngine,
            SoundDeviceAudioOutput,
            SpeechService,
            TTSConfig,
            TTSConfigurationError,
            TTSError,
        )
    except Exception as error:
        raise StartupError(f"TTS module import error: {error}") from error

    try:
        tts_config = TTSConfig.from_settings(app_config.tts)
        tts_engine = PiperTTSEngine(
            config=tts_config,
            logger=logging.getLogger("tts.engine"),
        )
        tts_output = SoundDeviceAudioOutput(
            output_device_index=tts_config.output_device_index,
            logger=logging.getLogger("tts.output"),
        )
        speech_service = SpeechService(
            engine=tts_engine,
            output=tts_output,
            logger=logging.getLogger("tts"),
        )
    except (TTSConfigurationError, TTSError) as error:
        raise StartupError(f"TTS initialization error: {error}") from error

    logger.info("TTS enabled")
    return speech_service


def _initialize_llm(
    *,
    app_config: Any,
    secret_config: Any,
    speech_service: Optional[Any],
    logger: logging.Logger,
) -> Optional[Any]:
    if not app_config.llm.enabled:
        if speech_service is not None:
            logger.warning(
                "TTS is enabled but LLM is disabled; no spoken reply will be generated."
            )
        return None

    try:
        from llm import LLMConfig, PomodoroAssistantLLM
    except Exception as error:
        raise StartupError(f"LLM module import error: {error}") from error

    try:
        llm_config = LLMConfig.from_sources(
            model_dir=app_config.llm.model_path,
            hf_filename=app_config.llm.hf_filename,
            hf_repo_id=app_config.llm.hf_repo_id or None,
            hf_revision=app_config.llm.hf_revision or None,
            hf_token=secret_config.hf_token,
            system_prompt_path=app_config.llm.system_prompt or None,
            n_threads=app_config.llm.n_threads,
            n_ctx=app_config.llm.n_ctx,
            n_batch=app_config.llm.n_batch,
            temperature=app_config.llm.temperature,
            top_p=app_config.llm.top_p,
            repeat_penalty=app_config.llm.repeat_penalty,
            verbose=app_config.llm.verbose,
            logger=logging.getLogger("llm.config"),
        )
        assistant_llm = PomodoroAssistantLLM(llm_config)
    except Exception as error:
        raise StartupError(f"LLM initialization error: {error}") from error

    logger.info("LLM enabled (model: %s)", llm_config.model_path)
    return assistant_llm


def _initialize_oracle_context(
    *,
    app_config: Any,
    secret_config: Any,
    assistant_llm: Optional[Any],
    logger: logging.Logger,
) -> Optional[Any]:
    if assistant_llm is None:
        return None

    try:
        from oracle import OracleConfig, OracleContextService

        oracle_config = OracleConfig.from_settings(
            app_config.oracle,
            calendar_id=secret_config.oracle_google_calendar_id,
            calendar_service_account_file=secret_config.oracle_google_service_account_file,
        )
        return OracleContextService(
            config=oracle_config,
            logger=logging.getLogger("oracle"),
        )
    except Exception as error:
        logger.warning("Oracle context disabled due to init error: %s", error)
        return None


def _initialize_ui_server(*, app_config: Any, logger: logging.Logger) -> Optional[Any]:
    try:
        from server import ServerConfigurationError, UIServer, UIServerConfig

        ui_server_config = UIServerConfig.from_settings(app_config.ui_server)
    except ServerConfigurationError as error:
        logger.error("UI server configuration error: %s", error)
        logger.warning("Continuing without UI server.")
        return None
    except Exception as error:
        logger.error("UI server initialization error: %s", error)
        logger.warning("Continuing without UI server.")
        return None

    if not ui_server_config.enabled:
        return None

    try:
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
        logger.error("UI server startup failed: %s", error)
        logger.warning("Continuing without UI server.")
        return None


def _run_runtime(
    *,
    logger: logging.Logger,
    app_config: Any,
    wake_word_config: Any,
    stt: Any,
    assistant_llm: Optional[Any],
    speech_service: Optional[Any],
    oracle_service: Optional[Any],
    ui_server: Optional[Any],
) -> int:
    try:
        from runtime import RuntimeBootstrap, RuntimeEngine, RuntimeHooks
    except Exception as error:
        raise StartupError(f"Runtime loop initialization error: {error}") from error

    runtime_bootstrap = RuntimeBootstrap(
        logger=logger,
        app_config=app_config,
        wake_word_config=wake_word_config,
        stt=stt,
        assistant_llm=assistant_llm,
        speech_service=speech_service,
        oracle_service=oracle_service,
        ui_server=ui_server,
        hooks=RuntimeHooks(
            setup_signal_handlers=setup_signal_handlers,
            wait_for_service_ready=wait_for_service_ready,
        ),
    )
    return RuntimeEngine(runtime_bootstrap).run()


def main() -> int:
    """Run the wake-word assistant runtime."""
    logger = setup_logging(level=logging.INFO)

    try:
        app_config, secret_config = _load_runtime_config(logger)
        wake_word_config, stt = _initialize_stt(
            app_config=app_config,
            secret_config=secret_config,
        )
        speech_service = _initialize_tts(
            app_config=app_config,
            logger=logger,
        )
        assistant_llm = _initialize_llm(
            app_config=app_config,
            secret_config=secret_config,
            speech_service=speech_service,
            logger=logger,
        )
        oracle_service = _initialize_oracle_context(
            app_config=app_config,
            secret_config=secret_config,
            assistant_llm=assistant_llm,
            logger=logger,
        )
        ui_server = _initialize_ui_server(app_config=app_config, logger=logger)
        return _run_runtime(
            logger=logger,
            app_config=app_config,
            wake_word_config=wake_word_config,
            stt=stt,
            assistant_llm=assistant_llm,
            speech_service=speech_service,
            oracle_service=oracle_service,
            ui_server=ui_server,
        )
    except StartupError as error:
        logger.error("%s", error)
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

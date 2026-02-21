from __future__ import annotations

import logging
import multiprocessing
import signal
import sys
import time
from typing import Any, Optional


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

    def signal_handler(signum: int, frame) -> None:
        signal_name = signal.Signals(signum).name
        print(f"\n👋 {signal_name} received, stopping...\n")
        service.stop()
        sys.exit(0)

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


def main() -> int:
    """Run the wake-word assistant runtime."""
    from app_config import (
        AppConfigurationError,
        load_app_config,
        load_secret_config,
        resolve_config_path,
    )

    logger = setup_logging(level=logging.INFO)

    try:
        config_path = resolve_config_path()
        app_config = load_app_config(str(config_path))
        secret_config = load_secret_config()
        logger.info("Loaded runtime config: %s", config_path)
    except AppConfigurationError as error:
        logger.error(f"App configuration error: {error}")
        return 1

    try:
        from stt import (
            ConfigurationError,
            FasterWhisperSTT,
            STTConfig,
            STTError,
            WakeWordConfig,
        )
    except Exception as error:
        logger.error("STT module import error: %s", error)
        return 1

    try:
        wake_word_config = WakeWordConfig.from_settings(
            pico_voice_access_key=secret_config.pico_voice_access_key,
            settings=app_config.wake_word,
        )
        stt_config = STTConfig.from_settings(app_config.stt)
    except ConfigurationError as error:
        logger.error(f"Configuration error: {error}")
        return 1

    stt_logger = logging.getLogger("stt")
    try:
        stt = FasterWhisperSTT(
            model_size=stt_config.model_size,
            device=stt_config.device,
            compute_type=stt_config.compute_type,
            language=stt_config.language,
            beam_size=stt_config.beam_size,
            vad_filter=stt_config.vad_filter,
            logger=stt_logger,
        )
    except STTError as error:
        logger.error(f"STT initialization error: {error}")
        return 1

    speech_service: Optional[Any] = None
    if app_config.tts.enabled:
        try:
            from tts import (
                PiperTTSEngine,
                SoundDeviceAudioOutput,
                SpeechService,
                TTSConfig,
                TTSError,
            )
        except Exception as error:
            logger.error("TTS module import error: %s", error)
            return 1

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
            logger.info("TTS enabled")
        except (ConfigurationError, TTSError) as error:
            logger.error(f"TTS initialization error: {error}")
            return 1

    assistant_llm: Optional[Any] = None
    llm_requested = app_config.llm.enabled
    if llm_requested:
        try:
            from llm import LLMConfig, PomodoroAssistantLLM

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
            logger.info("LLM enabled (model: %s)", llm_config.model_path)
        except Exception as error:
            logger.error(f"LLM initialization error: {error}")
            return 1
    elif speech_service:
        logger.warning(
            "TTS is enabled but LLM is disabled; no spoken reply will be generated."
        )

    oracle_service: Optional[Any] = None
    if assistant_llm:
        try:
            from oracle import OracleConfig, OracleContextService

            oracle_config = OracleConfig.from_settings(
                app_config.oracle,
                calendar_id=secret_config.oracle_google_calendar_id,
                calendar_service_account_file=secret_config.oracle_google_service_account_file,
            )
            oracle_service = OracleContextService(
                config=oracle_config, logger=logging.getLogger("oracle")
            )
        except Exception as error:
            logger.warning("Oracle context disabled due to init error: %s", error)

    ui_server: Optional[Any] = None
    ui_server_config: Optional[Any] = None

    try:
        from server import ServerConfigurationError, UIServer, UIServerConfig

        ui_server_config = UIServerConfig.from_settings(app_config.ui_server)
    except ServerConfigurationError as error:
        logger.error(f"UI server configuration error: {error}")
        logger.warning("Continuing without UI server.")
    except Exception as error:
        logger.error("UI server initialization error: %s", error)
        logger.warning("Continuing without UI server.")

    if ui_server_config and ui_server_config.enabled:
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
            ui_server.publish_state("idle", message="UI server connected")
        except Exception as error:
            logger.error(f"UI server startup failed: {error}")
            logger.warning("Continuing without UI server.")

    try:
        from runtime import run_runtime_loop
    except Exception as error:
        logger.error("Runtime loop initialization error: %s", error)
        return 1

    return run_runtime_loop(
        logger=logger,
        app_config=app_config,
        wake_word_config=wake_word_config,
        stt=stt,
        assistant_llm=assistant_llm,
        speech_service=speech_service,
        oracle_service=oracle_service,
        ui_server=ui_server,
        setup_signal_handlers_fn=setup_signal_handlers,
        wait_for_service_ready_fn=wait_for_service_ready,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

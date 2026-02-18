import logging
import os
import signal
import sys
import time
from datetime import datetime
from queue import Empty, Queue
from typing import Optional

from stt import (
    ConfigurationError,
    FasterWhisperSTT,
    QueueEventPublisher,
    STTConfig,
    STTError,
    UtteranceCapturedEvent,
    WakeWordConfig,
    WakeWordDetectedEvent,
    WakeWordErrorEvent,
    WakeWordService,
)
from tts import (
    CoquiTTSEngine,
    SoundDeviceAudioOutput,
    SpeechService,
    TTSConfig,
    TTSError,
)
from llm import EnvironmentContext, LLMConfig, PomodoroAssistantLLM
from oracle import OracleContextService
from server import ServerConfigurationError, UIServer, UIServerConfig


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure logging for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("wake_word_app")


def setup_signal_handlers(service: WakeWordService) -> None:
    """Set up graceful shutdown on SIGTERM and SIGINT."""

    def signal_handler(signum: int, frame) -> None:
        signal_name = signal.Signals(signum).name
        print(f"\n👋 {signal_name} received, stopping...\n")
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def wait_for_service_ready(service: WakeWordService, timeout: float = 10.0) -> bool:
    """Wait for service to become ready, with fast-fail on crash.

    Args:
        service: The wake word service
        timeout: Maximum time to wait in seconds

    Returns:
        True if service became ready, False if it failed or timed out
    """
    start_time = time.time()
    poll_interval = 0.1

    while time.time() - start_time < timeout:
        if service.is_ready:
            return True

        # Fast-fail: if service died during startup, don't wait full timeout
        if not service.is_running:
            return False

        time.sleep(poll_interval)

    return service.is_ready


def main() -> int:
    """Run the wake word detection service."""
    logger = setup_logging(level=logging.INFO)

    # Load configurations
    try:
        config = WakeWordConfig.from_environment()
        stt_config = STTConfig.from_environment()
    except ConfigurationError as error:
        logger.error(f"Configuration error: {error}")
        return 1

    # Create STT service
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

    # Optional TTS service
    speech_service: Optional[SpeechService] = None
    if os.getenv("TTS_ENABLED", "false").lower() == "true":
        try:
            tts_config = TTSConfig.from_environment()
            tts_engine = CoquiTTSEngine(
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

    # Optional LLM service
    assistant_llm: Optional[PomodoroAssistantLLM] = None
    llm_requested = any(
        (
            os.getenv("LLM_MODEL_PATH", "").strip(),
            os.getenv("LLM_HF_REPO_ID", "").strip(),
            os.getenv("ENABLE_LLM", "false").lower() == "true",
        )
    )
    if llm_requested:
        try:
            llm_config = LLMConfig.from_environment()
            assistant_llm = PomodoroAssistantLLM(llm_config)
            logger.info("LLM enabled (model: %s)", llm_config.model_path)
        except Exception as error:
            logger.error(f"LLM initialization error: {error}")
            return 1
    elif speech_service:
        logger.warning(
            "TTS is enabled but LLM_MODEL_PATH is not set; no spoken reply will be generated."
        )

    # Optional oracle context providers (sensors/calendar) for LLM environment block
    oracle_service: Optional[OracleContextService] = None
    if assistant_llm:
        try:
            oracle_service = OracleContextService.from_environment(
                logger=logging.getLogger("oracle")
            )
        except Exception as error:
            logger.warning("Oracle context disabled due to init error: %s", error)

    def build_llm_environment_context() -> EnvironmentContext:
        payload = {
            "now_local": datetime.now().astimezone().isoformat(timespec="seconds"),
            "light_level_lux": None,
            "air_quality": None,
            "upcoming_events": None,
        }
        if oracle_service is not None:
            try:
                payload.update(oracle_service.build_environment_payload())
            except Exception as error:
                logger.warning("Failed to collect oracle context: %s", error)

        return EnvironmentContext(
            now_local=payload["now_local"],
            light_level_lux=payload.get("light_level_lux"),
            air_quality=payload.get("air_quality"),
            upcoming_events=payload.get("upcoming_events"),
        )

    # Optional UI server for static page + websocket updates
    ui_server: Optional[UIServer] = None
    ui_server_config: Optional[UIServerConfig] = None
    try:
        ui_server_config = UIServerConfig.from_environment()
    except ServerConfigurationError as error:
        logger.error(f"UI server configuration error: {error}")
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

    def publish_ui(event_type: str, **payload) -> None:
        if ui_server:
            ui_server.publish(event_type, **payload)

    def publish_ui_state(
        state: str,
        *,
        message: Optional[str] = None,
        **payload,
    ) -> None:
        if ui_server:
            ui_server.publish_state(state, message=message, **payload)

    # Create wake word service
    event_queue: Queue = Queue()
    publisher = QueueEventPublisher(event_queue)
    service: Optional[WakeWordService] = None
    wake_word_logger = logging.getLogger("wake_word")

    try:
        service = WakeWordService(
            config=config,
            publisher=publisher,
            logger=wake_word_logger,
        )

        setup_signal_handlers(service)

        logger.info("Starting wake word service...")
        service.start()

        # Wait for service to be ready (with fast-fail on crash)
        logger.debug("Initializing wake word detection...")
        if not wait_for_service_ready(service, timeout=10.0):
            # Check if service crashed vs. timed out
            if not service.is_running:
                logger.error("Service crashed during initialization.")
            else:
                logger.error("Service initialization timed out.")

            return 1

        logger.info("Ready! Listening for wake word ...")
        publish_ui_state("idle", message="Listening for wake word")

        # Main event loop
        while True:
            try:
                event = event_queue.get(timeout=1.0)
            except Empty:
                if not service.is_running:
                    logger.error("Service stopped unexpectedly")
                    publish_ui(
                        "error",
                        state="error",
                        message="Wake word service stopped unexpectedly",
                    )
                    return 1
                continue

            if isinstance(event, WakeWordDetectedEvent):
                print(f"[{event.occurred_at.isoformat()}] 🎤 WakeWordDetectedEvent\n")
                publish_ui_state("listening", message="Wake word detected")

            elif isinstance(event, UtteranceCapturedEvent):
                utterance = event.utterance
                print(
                    f"[{utterance.created_at.isoformat()}] ✓ UtteranceCapturedEvent: "
                    f"{utterance.duration_seconds:.2f}s, {len(utterance.audio_bytes):,} bytes\n"
                )
                publish_ui_state(
                    "transcribing",
                    message="Transcribing utterance",
                    duration_seconds=round(utterance.duration_seconds, 2),
                    audio_bytes=len(utterance.audio_bytes),
                )

                # Transcribe the utterance
                print("  ⏳ Transcribing...\n", end="", flush=True)
                try:
                    result = stt.transcribe(utterance)
                    if result.text:
                        confidence_str = (
                            f" (confidence: {result.confidence:.0%})"
                            if result.confidence
                            else ""
                        )
                        print(f'\r  💬 "{result.text}"{confidence_str}\n')
                        publish_ui(
                            "transcript",
                            state="transcribing",
                            text=result.text,
                            language=result.language,
                            confidence=result.confidence,
                        )

                        if assistant_llm:
                            publish_ui_state("thinking", message="Generating reply")
                            try:
                                env_context = build_llm_environment_context()
                                llm_response = assistant_llm.run(
                                    result.text,
                                    env=env_context,
                                )
                                assistant_text = llm_response["assistant_text"].strip()
                                print(f'  🤖 "{assistant_text}"\n')
                                publish_ui(
                                    "assistant_reply",
                                    state="replying",
                                    text=assistant_text,
                                )
                                # Tool handling intentionally skipped for now.
                                if speech_service and assistant_text:
                                    speech_service.speak(assistant_text)
                                publish_ui_state(
                                    "idle",
                                    message="Listening for wake word",
                                )
                            except TTSError as error:
                                logger.error(f"TTS playback failed: {error}")
                                publish_ui(
                                    "error",
                                    state="error",
                                    message=f"TTS playback failed: {error}",
                                )
                                publish_ui_state(
                                    "idle",
                                    message="Listening for wake word",
                                )
                            except Exception as error:
                                logger.error(f"LLM processing failed: {error}")
                                publish_ui(
                                    "error",
                                    state="error",
                                    message=f"LLM processing failed: {error}",
                                )
                                publish_ui_state(
                                    "idle",
                                    message="Listening for wake word",
                                )
                        else:
                            publish_ui_state(
                                "idle",
                                message="Listening for wake word",
                            )
                    else:
                        print("\r  ⚠️  No speech detected\n")
                        publish_ui_state("idle", message="No speech detected")
                except STTError as error:
                    logger.error(f"Transcription failed: {error}")
                    publish_ui(
                        "error",
                        state="error",
                        message=f"Transcription failed: {error}",
                    )
                    publish_ui_state("idle", message="Listening for wake word")

            elif isinstance(event, WakeWordErrorEvent):
                logger.error(
                    f"WakeWordErrorEvent: {event.message}", exc_info=event.exception
                )
                publish_ui(
                    "error",
                    state="error",
                    message=f"WakeWordErrorEvent: {event.message}",
                )
                return 1

    except KeyboardInterrupt:
        print("\n👋 Shutting down...\n")
        return 0

    except Exception as error:
        logger.error(f"Unexpected error: {error}", exc_info=True)
        return 1

    finally:
        if service:
            logger.info("Stopping service...")
            try:
                service.stop(timeout_seconds=5.0)
            except Exception as error:
                logger.error(f"Error stopping service: {error}", exc_info=True)
        if ui_server:
            logger.info("Stopping UI server...")
            try:
                ui_server.stop(timeout_seconds=5.0)
            except Exception as error:
                logger.error(f"Error stopping UI server: {error}", exc_info=True)


if __name__ == "__main__":
    sys.exit(main())

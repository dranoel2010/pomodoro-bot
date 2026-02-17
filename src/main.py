import logging
import os
import signal
import sys
import time
from queue import Empty, Queue
from typing import Optional

from wake_word import (
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
    if os.getenv("ENABLE_TTS", "false").lower() == "true":
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

        # Main event loop
        while True:
            try:
                event = event_queue.get(timeout=1.0)
            except Empty:
                if not service.is_running:
                    logger.error("Service stopped unexpectedly")
                    return 1
                continue

            if isinstance(event, WakeWordDetectedEvent):
                print(f"[{event.occurred_at.isoformat()}] 🎤 WakeWordDetectedEvent\n")

            elif isinstance(event, UtteranceCapturedEvent):
                utterance = event.utterance
                print(
                    f"[{utterance.created_at.isoformat()}] ✓ UtteranceCapturedEvent: "
                    f"{utterance.duration_seconds:.2f}s, {len(utterance.audio_bytes):,} bytes\n"
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
                        if speech_service:
                            try:
                                speech_service.speak(result.text)
                            except TTSError as error:
                                logger.error(f"TTS playback failed: {error}")
                    else:
                        print("\r  ⚠️  No speech detected\n")
                except STTError as error:
                    logger.error(f"Transcription failed: {error}")

            elif isinstance(event, WakeWordErrorEvent):
                logger.error(
                    f"WakeWordErrorEvent: {event.message}", exc_info=event.exception
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


if __name__ == "__main__":
    sys.exit(main())

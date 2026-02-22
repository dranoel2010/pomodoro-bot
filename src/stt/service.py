"""Wake-word detection service coordinating Porcupine and utterance capture."""

import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import pvporcupine
from pvrecorder import PvRecorder

from .capture import UtteranceCapture
from .config import WakeWordConfig
from .events import (
    EventPublisher,
    UtteranceCapturedEvent,
    WakeWordDetectedEvent,
    WakeWordErrorEvent,
)
from .vad import VoiceActivityDetector


class WakeWordService:
    """Service for wake word detection and utterance capture."""

    def __init__(
        self,
        config: WakeWordConfig,
        publisher: EventPublisher,
        logger: Optional[logging.Logger] = None,
    ):
        self._config = config
        self._publisher = publisher
        self._logger = logger or logging.getLogger(__name__)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()  # NEW: Signals when ready to detect
        self._running_lock = threading.Lock()
        self._running = False

        # Initialize VAD
        self._vad = VoiceActivityDetector(
            energy_threshold=config.energy_threshold,
            adaptive_multiplier=config.adaptive_threshold_multiplier,
            adaptive=True,
            logger=self._logger.getChild("vad"),
        )

        # Initialize utterance capture
        self._capture = UtteranceCapture(
            vad=self._vad,
            silence_timeout_seconds=config.silence_timeout_seconds,
            max_utterance_seconds=config.max_utterance_seconds,
            no_speech_timeout_seconds=config.no_speech_timeout_seconds,
            min_speech_seconds=config.min_speech_seconds,
            logger=self._logger.getChild("capture"),
        )

    @property
    def is_running(self) -> bool:
        """Check if the service is currently running."""
        with self._running_lock:
            return (
                self._running and self._thread is not None and self._thread.is_alive()
            )

    @property
    def is_ready(self) -> bool:
        """Check if the service is ready to detect wake words."""
        return self._ready_event.is_set()

    def wait_until_ready(self, timeout: Optional[float] = None) -> bool:
        """Wait until the service is ready to detect wake words.

        Args:
            timeout: Maximum time to wait in seconds. None means wait forever.

        Returns:
            True if service became ready, False if timeout expired.
        """
        return self._ready_event.wait(timeout=timeout)

    def start(self) -> None:
        """Start the wake word detection service."""
        with self._running_lock:
            if self._running and self._thread is not None and self._thread.is_alive():
                self._logger.warning("Service is already running")
                return

            self._logger.debug("Starting wake word service")
            self._stop_event.clear()
            self._ready_event.clear()  # Reset ready state
            self._running = True

            self._thread = threading.Thread(
                target=self._run, daemon=True, name="wake-word-service"
            )
            self._thread.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """Stop the wake word detection service.

        Args:
            timeout_seconds: Maximum time to wait for graceful shutdown.
        """
        with self._running_lock:
            if not self._running:
                self._logger.warning("Service is not running")
                return

        self._logger.debug("Stopping wake word service")
        self._stop_event.set()
        self._ready_event.clear()  # Clear ready state

        if self._thread:
            self._thread.join(timeout=timeout_seconds)

            if self._thread.is_alive():
                self._logger.error(
                    f"Service thread did not stop within {timeout_seconds}s. "
                    "Thread may still be running (daemon will be killed on exit)."
                )
                # Do NOT set _running to False here - thread is still alive
            else:
                self._logger.debug("Service stopped successfully")
                with self._running_lock:
                    self._running = False

    @contextmanager
    def _create_resources(self):
        """Context manager for Porcupine and PvRecorder resources."""
        porcupine = None
        recorder = None

        try:
            self._logger.debug("Initializing Porcupine wake word engine")
            porcupine = pvporcupine.create(
                access_key=self._config.pico_voice_access_key,
                keyword_paths=[self._config.porcupine_wake_word_file],
                model_path=self._config.porcupine_model_params_file,
            )

            self._logger.debug(
                f"Initializing audio recorder (device {self._config.device_index})"
            )
            recorder = PvRecorder(
                frame_length=porcupine.frame_length,
                device_index=self._config.device_index,
            )
            recorder.start()

            yield porcupine, recorder

        finally:
            if recorder:
                self._logger.debug("Cleaning up recorder")
                try:
                    recorder.stop()
                    recorder.delete()
                except Exception as e:
                    self._logger.error(f"Error cleaning up recorder: {e}")

            if porcupine:
                self._logger.debug("Cleaning up Porcupine")
                try:
                    porcupine.delete()
                except Exception as e:
                    self._logger.error(f"Error cleaning up Porcupine: {e}")

    def _calibrate_noise_floor(
        self, recorder: PvRecorder, sample_rate: int, frame_length: int
    ) -> None:
        """Calibrate noise floor by sampling ambient audio."""
        self._logger.debug("Calibrating noise floor...")

        frames_per_second = sample_rate / frame_length
        calibration_frames = int(
            self._config.noise_floor_calibration_seconds * frames_per_second
        )

        noise_frames = []
        for _ in range(max(1, calibration_frames)):
            if self._stop_event.is_set():
                return
            pcm = recorder.read()
            noise_frames.append(pcm)

        noise_floor = VoiceActivityDetector.calculate_noise_floor(noise_frames)
        self._vad.set_noise_floor(noise_floor)

    def _run(self) -> None:
        """Main service loop."""
        try:
            with self._create_resources() as (porcupine, recorder):
                # Calibrate noise floor for adaptive thresholding
                self._calibrate_noise_floor(
                    recorder, porcupine.sample_rate, porcupine.frame_length
                )

                # Signal that we're ready to detect wake words
                self._ready_event.set()
                self._logger.debug(
                    "Wake word service ready, listening for wake word..."
                )

                while not self._stop_event.is_set():
                    pcm = recorder.read()
                    detection_index = porcupine.process(pcm)

                    if detection_index >= 0:
                        self._logger.debug("Wake word detected!")
                        self._publisher.publish(
                            WakeWordDetectedEvent(
                                occurred_at=datetime.now(timezone.utc)
                            )
                        )

                        utterance = self._capture.capture(
                            recorder,
                            porcupine.sample_rate,
                            porcupine.frame_length,
                            self._stop_event,
                        )

                        if utterance:
                            self._publisher.publish(
                                UtteranceCapturedEvent(utterance=utterance)
                            )
                        else:
                            self._logger.warning("No valid utterance captured")

        except Exception as error:
            self._logger.error(f"Wake word service error: {error}", exc_info=True)
            self._publisher.publish(
                WakeWordErrorEvent(
                    occurred_at=datetime.now(timezone.utc),
                    message=str(error),
                    exception=error,
                )
            )
        finally:
            self._ready_event.clear()  # No longer ready
            with self._running_lock:
                self._running = False
            self._logger.debug("Wake word service terminated")

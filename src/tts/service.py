"""High-level speech service that synthesizes and plays assistant replies."""

import logging
import time

from .engine import PiperTTSEngine
from .output import SoundDeviceAudioOutput


class SpeechService:
    """Combines synthesis and playback into a single speak operation."""
    def __init__(
        self,
        engine: PiperTTSEngine,
        output: SoundDeviceAudioOutput,
        logger: logging.Logger | None = None,
    ):
        self._engine = engine
        self._output = output
        self._logger = logger or logging.getLogger(__name__)

    def speak(self, text: str) -> None:
        synthesis_started_at = time.perf_counter()
        wav, sample_rate_hz = self._engine.synthesize(text)
        synthesis_duration_seconds = time.perf_counter() - synthesis_started_at
        self._logger.debug(
            "Playing %d samples of synthesized audio at %d Hz (tts_synthesis_ms=%d)",
            len(wav),
            sample_rate_hz,
            round(synthesis_duration_seconds * 1000),
        )
        playback_started_at = time.perf_counter()
        self._output.play(wav, sample_rate_hz)
        playback_duration_seconds = time.perf_counter() - playback_started_at
        self._logger.info(
            "TTS stage metrics: synthesis_ms=%d playback_ms=%d samples=%d sample_rate_hz=%d",
            round(synthesis_duration_seconds * 1000),
            round(playback_duration_seconds * 1000),
            len(wav),
            sample_rate_hz,
        )

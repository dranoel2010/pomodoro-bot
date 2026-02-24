"""High-level speech service that synthesizes and plays assistant replies."""

import logging

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
        wav, sample_rate_hz = self._engine.synthesize(text)
        self._logger.debug(
            "Playing %d samples of synthesized audio at %d Hz",
            len(wav),
            sample_rate_hz,
        )
        self._output.play(wav, sample_rate_hz)

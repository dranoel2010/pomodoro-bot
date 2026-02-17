import logging
from typing import Optional

from .engine import CoquiTTSEngine
from .output import SoundDeviceAudioOutput


class SpeechService:
    def __init__(
        self,
        engine: CoquiTTSEngine,
        output: SoundDeviceAudioOutput,
        logger: Optional[logging.Logger] = None,
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

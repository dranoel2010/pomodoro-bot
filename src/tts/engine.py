import logging
from typing import Optional

import numpy as np

from .config import TTSConfig


class TTSError(Exception):
    """Raised when text-to-speech processing fails."""

    pass


class CoquiTTSEngine:
    def __init__(
        self,
        config: TTSConfig,
        logger: Optional[logging.Logger] = None,
    ):
        self._config = config
        self._logger = logger or logging.getLogger(__name__)

        try:
            from TTS.api import TTS

            self._tts = TTS(
                model_path=self._config.model_path,
                config_path=self._config.config_path,
                gpu=self._config.gpu,
                progress_bar=False,
            )
        except Exception as error:
            raise TTSError(f"Failed to initialize TTS engine: {error}") from error

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        if not text.strip():
            raise TTSError("Text to synthesize cannot be empty")

        try:
            wav = np.asarray(self._tts.tts(text), dtype=np.float32)
            sample_rate_hz = self._tts.synthesizer.output_sample_rate
            return wav, sample_rate_hz
        except Exception as error:
            raise TTSError(f"TTS synthesis failed: {error}") from error

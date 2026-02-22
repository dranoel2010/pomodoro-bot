"""Sounddevice-backed audio playback for synthesized speech."""

import logging
from typing import Optional

import numpy as np
import sounddevice as sd

from .engine import TTSError


class SoundDeviceAudioOutput:
    """Plays mono PCM arrays through a selected sounddevice output."""
    def __init__(
        self,
        output_device_index: Optional[int] = None,
        blocksize: int = 2048,
        logger: Optional[logging.Logger] = None,
    ):
        self._output_device_index = output_device_index
        self._blocksize = blocksize
        self._logger = logger or logging.getLogger(__name__)

    def play(self, wav: np.ndarray, sample_rate_hz: int, blocking: bool = True) -> None:
        if wav.ndim != 1:
            raise TTSError("Expected mono PCM array for playback")
        if len(wav) == 0:
            raise TTSError("Cannot play empty audio buffer")

        pos = 0

        def callback(outdata, frames, time_info, status):
            nonlocal pos
            if status:
                self._logger.warning("Sounddevice status: %s", status)

            end = pos + frames
            chunk = wav[pos:end]

            if len(chunk) < frames:
                outdata[: len(chunk), 0] = chunk
                outdata[len(chunk) :, 0] = 0
                raise sd.CallbackStop()

            outdata[:, 0] = chunk
            pos = end

        try:
            with sd.OutputStream(
                channels=1,
                samplerate=sample_rate_hz,
                blocksize=self._blocksize,
                callback=callback,
                device=self._output_device_index,
            ):
                if blocking:
                    sd.sleep(int(len(wav) / sample_rate_hz * 1000) + 200)
        except Exception as error:
            raise TTSError(f"Audio playback failed: {error}") from error

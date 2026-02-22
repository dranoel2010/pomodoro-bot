"""Energy-based voice activity detector used during utterance capture."""

import logging
import math
from typing import Optional


class VoiceActivityDetector:
    """Voice activity detection using energy-based thresholding."""

    def __init__(
        self,
        energy_threshold: float,
        adaptive_multiplier: float = 2.0,
        adaptive: bool = True,
        logger: Optional[logging.Logger] = None,
    ):
        self._base_threshold = energy_threshold
        self._adaptive = adaptive
        self._noise_floor: Optional[float] = None
        self._adaptive_multiplier = adaptive_multiplier
        self._logger = logger or logging.getLogger(__name__)

    def set_noise_floor(self, noise_floor: float) -> None:
        """Set the baseline noise floor for adaptive thresholding."""
        self._noise_floor = noise_floor
        self._logger.debug(f"Noise floor calibrated: {noise_floor:.2f}")

    @property
    def threshold(self) -> float:
        """Get the current threshold (adaptive or fixed).

        Uses the maximum of the base threshold and adaptive threshold
        to prevent overly sensitive detection in very quiet environments.
        """
        if self._adaptive and self._noise_floor is not None:
            adaptive_threshold = self._noise_floor * self._adaptive_multiplier
            return max(self._base_threshold, adaptive_threshold)
        return self._base_threshold

    def is_voice_active(self, pcm: list[int]) -> bool:
        """Detect if voice is present in audio frame using RMS energy."""
        if not pcm:
            return False

        # Calculate RMS (Root Mean Square) energy
        mean_square = sum(sample * sample for sample in pcm) / len(pcm)
        rms = math.sqrt(mean_square)

        return rms >= self.threshold

    @staticmethod
    def calculate_noise_floor(frames: list[list[int]]) -> float:
        """Calculate average RMS energy across multiple frames."""
        if not frames:
            return 0.0

        total_rms = 0.0
        for pcm in frames:
            if pcm:
                mean_square = sum(sample * sample for sample in pcm) / len(pcm)
                total_rms += math.sqrt(mean_square)

        return total_rms / len(frames) if frames else 0.0

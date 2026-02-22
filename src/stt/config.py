"""Configuration models for wake-word and STT components."""

import os
from dataclasses import dataclass
from typing import Optional


class ConfigurationError(Exception):
    """Raised when configuration is invalid."""

    pass


@dataclass(frozen=True)
class WakeWordConfig:
    """Validated wake-word and capture configuration for `WakeWordService`."""
    pico_voice_access_key: str
    porcupine_wake_word_file: str
    porcupine_model_params_file: str
    device_index: int = 0
    silence_timeout_seconds: float = 1.5  # Increased from 1.0
    max_utterance_seconds: float = 10.0
    no_speech_timeout_seconds: float = 3.0
    min_speech_seconds: float = 0.15  # Reduced from 0.2 - allow shorter utterances
    energy_threshold: float = 100  # Reduced from 500.0 - more sensitive
    noise_floor_calibration_seconds: float = 1.0
    adaptive_threshold_multiplier: float = 1.5  # Reduced from 2.0 - less aggressive
    validate_paths: bool = True

    def __post_init__(self):
        """Validate configuration on initialization."""
        if not self.pico_voice_access_key:
            raise ConfigurationError("pico_voice_access_key cannot be empty")
        if not self.porcupine_wake_word_file:
            raise ConfigurationError("PORCUPINE_PPN_FILE cannot be empty")
        if not self.porcupine_model_params_file:
            raise ConfigurationError("porcupine_model_params_file cannot be empty")

        if self.validate_paths:
            if not os.path.exists(self.porcupine_wake_word_file):
                raise ConfigurationError(
                    f"PORCUPINE_PPN_FILE does not exist: {self.porcupine_wake_word_file}"
                )
            if not os.path.exists(self.porcupine_model_params_file):
                raise ConfigurationError(
                    f"porcupine_model_params_file does not exist: {self.porcupine_model_params_file}"
                )

        # Validate all timing parameters
        if self.silence_timeout_seconds <= 0:
            raise ConfigurationError("silence_timeout_seconds must be positive")
        if self.max_utterance_seconds <= 0:
            raise ConfigurationError("max_utterance_seconds must be positive")
        if self.min_speech_seconds <= 0:
            raise ConfigurationError("min_speech_seconds must be positive")
        if self.no_speech_timeout_seconds <= 0:
            raise ConfigurationError("no_speech_timeout_seconds must be positive")
        if self.noise_floor_calibration_seconds <= 0:
            raise ConfigurationError("noise_floor_calibration_seconds must be positive")

        # Validate thresholds
        if self.energy_threshold <= 0:
            raise ConfigurationError("energy_threshold must be positive")
        if self.adaptive_threshold_multiplier <= 0:
            raise ConfigurationError("adaptive_threshold_multiplier must be positive")

    @classmethod
    def from_settings(
        cls,
        *,
        pico_voice_access_key: str,
        settings,
    ) -> "WakeWordConfig":
        return cls(
            pico_voice_access_key=pico_voice_access_key,
            porcupine_wake_word_file=settings.ppn_file,
            porcupine_model_params_file=settings.pv_file,
            device_index=settings.device_index,
            silence_timeout_seconds=settings.silence_timeout_seconds,
            max_utterance_seconds=settings.max_utterance_seconds,
            no_speech_timeout_seconds=settings.no_speech_timeout_seconds,
            min_speech_seconds=settings.min_speech_seconds,
            energy_threshold=settings.energy_threshold,
            noise_floor_calibration_seconds=settings.noise_floor_calibration_seconds,
            adaptive_threshold_multiplier=settings.adaptive_threshold_multiplier,
            validate_paths=settings.validate_paths,
        )

@dataclass(frozen=True)
class STTConfig:
    """Speech-to-text model configuration passed to faster-whisper adapters."""
    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: Optional[str] = "en"
    beam_size: int = 5
    vad_filter: bool = True

    @classmethod
    def from_settings(cls, settings) -> "STTConfig":
        return cls(
            model_size=settings.model_size,
            device=settings.device,
            compute_type=settings.compute_type,
            language=settings.language,
            beam_size=settings.beam_size,
            vad_filter=settings.vad_filter,
        )

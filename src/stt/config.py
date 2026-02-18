import os
from dataclasses import dataclass
from typing import Optional


class ConfigurationError(Exception):
    """Raised when configuration is invalid."""

    pass


@dataclass(frozen=True)
class WakeWordConfig:
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
    def from_environment(cls) -> "WakeWordConfig":
        """Create configuration from environment variables.

        Raises:
            ConfigurationError: If required environment variables are missing or invalid.
        """
        pico_key = os.getenv("PICO_VOICE_ACCESS_KEY")
        wake_word_ppn_file = os.getenv("PORCUPINE_PPN_FILE")
        model_params_file = os.getenv("PORCUPINE_PV_FILE")

        if not pico_key:
            raise ConfigurationError(
                "PICO_VOICE_ACCESS_KEY environment variable is required"
            )
        if not wake_word_ppn_file:
            raise ConfigurationError(
                "PORCUPINE_PPN_FILE environment variable is required"
            )
        if not model_params_file:
            raise ConfigurationError(
                "PORCUPINE_PV_FILE environment variable is required"
            )

        return cls(
            pico_voice_access_key=pico_key,
            porcupine_wake_word_file=wake_word_ppn_file,
            porcupine_model_params_file=model_params_file,
        )


@dataclass(frozen=True)
class STTConfig:
    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: Optional[str] = "en"
    beam_size: int = 5
    vad_filter: bool = True

    @classmethod
    def from_environment(cls) -> "STTConfig":
        """Create STT configuration from environment variables.

        Raises:
            ConfigurationError: If environment variables are invalid.
        """
        import os

        # Handle language setting - support "auto" or "none" for auto-detection
        language = os.getenv("WHISPER_LANGUAGE", "en")
        if language.lower() in ("auto", "none", "null", ""):
            language = None

        # Parse beam_size with validation
        beam_size_str = os.getenv("WHISPER_BEAM_SIZE", "5")
        try:
            beam_size = int(beam_size_str)
            if beam_size < 1:
                raise ConfigurationError(
                    f"WHISPER_BEAM_SIZE must be >= 1, got: {beam_size}"
                )
        except ValueError:
            raise ConfigurationError(
                f"WHISPER_BEAM_SIZE must be an integer, got: {beam_size_str}"
            )

        return cls(
            model_size=os.getenv("WHISPER_MODEL_SIZE", "base"),
            device=os.getenv("WHISPER_DEVICE", "cpu"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            language=language,
            beam_size=beam_size,
            vad_filter=os.getenv("WHISPER_VAD_FILTER", "true").lower() == "true",
        )

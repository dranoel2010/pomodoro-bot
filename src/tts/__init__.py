"""Public exports for text-to-speech components."""

from .config import TTSConfig, TTSConfigurationError
from .engine import PiperTTSEngine, TTSError
from .output import SoundDeviceAudioOutput
from .service import SpeechService

__all__ = [
    "TTSConfig",
    "TTSConfigurationError",
    "TTSError",
    "PiperTTSEngine",
    "SoundDeviceAudioOutput",
    "SpeechService",
]

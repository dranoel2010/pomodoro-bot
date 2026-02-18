"""Wake word detection service using Porcupine."""

from .capture import UtteranceCapture
from .config import ConfigurationError, WakeWordConfig, STTConfig
from .events import (
    EventPublisher,
    QueueEventPublisher,
    Utterance,
    UtteranceCapturedEvent,
    WakeWordDetectedEvent,
    WakeWordErrorEvent,
    WakeWordEvent,
)
from .stt import (
    FasterWhisperSTT,
    StreamingFasterWhisperSTT,
    STTError,
    TranscriptionResult,
)
from .service import WakeWordService
from .vad import VoiceActivityDetector

__all__ = [
    # Config
    "WakeWordConfig",
    "ConfigurationError",
    # Events
    "Utterance",
    "WakeWordDetectedEvent",
    "UtteranceCapturedEvent",
    "WakeWordErrorEvent",
    "WakeWordEvent",
    "EventPublisher",
    "QueueEventPublisher",
    # Components
    "VoiceActivityDetector",
    "UtteranceCapture",
    # STT
    "FasterWhisperSTT",
    "StreamingFasterWhisperSTT",
    "STTError",
    "TranscriptionResult",
    "STTConfig",
    # Service
    "WakeWordService",
]

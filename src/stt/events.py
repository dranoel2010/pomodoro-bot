"""Event dataclasses and publisher contracts emitted by wake-word services."""

from dataclasses import dataclass
from datetime import datetime
from queue import Queue
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Utterance:
    """Captured PCM utterance payload passed from wake-word service to runtime."""
    audio_bytes: bytes
    sample_rate_hz: int
    created_at: datetime

    @property
    def duration_seconds(self) -> float:
        """Calculate utterance duration from audio data."""
        # Each sample is 2 bytes (16-bit PCM)
        sample_count = len(self.audio_bytes) // 2
        return sample_count / self.sample_rate_hz


@dataclass(frozen=True, slots=True)
class WakeWordDetectedEvent:
    """Event emitted when Porcupine detects the wake word."""
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class UtteranceCapturedEvent:
    """Event emitted when an utterance has been captured after wake-word detection."""
    utterance: Utterance


@dataclass(frozen=True, slots=True)
class WakeWordErrorEvent:
    """Event emitted when wake-word capture fails unexpectedly."""
    occurred_at: datetime
    message: str
    exception: Exception | None = None


WakeWordEvent = WakeWordDetectedEvent | UtteranceCapturedEvent | WakeWordErrorEvent


class EventPublisher(Protocol):
    """Protocol for publishing wake word events."""

    def publish(self, event: WakeWordEvent) -> None: ...


class QueueEventPublisher:
    """Event publisher that pushes events to a queue."""

    def __init__(self, queue: Queue):
        self._queue = queue

    def publish(self, event: WakeWordEvent) -> None:
        self._queue.put(event)

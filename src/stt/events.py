from dataclasses import dataclass
from datetime import datetime
from queue import Queue
from typing import Optional, Protocol


@dataclass(frozen=True)
class Utterance:
    audio_bytes: bytes
    sample_rate_hz: int
    created_at: datetime

    @property
    def duration_seconds(self) -> float:
        """Calculate utterance duration from audio data."""
        # Each sample is 2 bytes (16-bit PCM)
        sample_count = len(self.audio_bytes) // 2
        return sample_count / self.sample_rate_hz


@dataclass(frozen=True)
class WakeWordDetectedEvent:
    occurred_at: datetime


@dataclass(frozen=True)
class UtteranceCapturedEvent:
    utterance: Utterance


@dataclass(frozen=True)
class WakeWordErrorEvent:
    occurred_at: datetime
    message: str
    exception: Optional[Exception] = None


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

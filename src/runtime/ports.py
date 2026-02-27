"""Runtime-facing protocol interfaces for core collaborators."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Protocol

if TYPE_CHECKING:
    from llm.types import EnvironmentContext, StructuredResponse
    from stt.config import WakeWordConfig
    from stt.events import EventPublisher, Utterance
    from stt.stt import TranscriptionResult


class STTClient(Protocol):
    def transcribe(self, utterance: "Utterance") -> "TranscriptionResult":
        ...


class LLMClient(Protocol):
    def run(
        self,
        user_prompt: str,
        *,
        env: "EnvironmentContext" | None = None,
        extra_context: str | None = None,
        max_tokens: int | None = None,
    ) -> "StructuredResponse":
        ...


class SpeechClient(Protocol):
    def speak(self, text: str) -> None:
        ...


class OracleContextClient(Protocol):
    def build_environment_payload(self) -> dict[str, object]:
        ...

    def list_upcoming_events(
        self,
        *,
        max_results: int | None = None,
        time_min: datetime | None = None,
    ) -> list[dict[str, object]]:
        ...

    def add_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
    ) -> str:
        ...


class UIServerPort(Protocol):
    def publish(self, event_type: str, **payload: object) -> None:
        ...

    def publish_state(
        self,
        state: str,
        *,
        message: str | None = None,
        **payload: object,
    ) -> None:
        ...

    def stop(self, timeout_seconds: float = 5.0) -> None:
        ...


class WakeWordServicePort(Protocol):
    @property
    def is_running(self) -> bool:
        ...

    @property
    def is_ready(self) -> bool:
        ...

    def wait_until_ready(self, timeout: float | None = None) -> bool:
        ...

    def start(self) -> None:
        ...

    def stop(self, timeout_seconds: float = 5.0) -> None:
        ...


WakeWordServiceFactory = Callable[
    ["WakeWordConfig", "EventPublisher", logging.Logger],
    WakeWordServicePort,
]

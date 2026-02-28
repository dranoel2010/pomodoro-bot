from __future__ import annotations

"""Pipeline-facing Protocol contracts for STT, LLM, and TTS worker dependencies."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from llm.types import EnvironmentContext, StructuredResponse
    from stt.events import Utterance
    from stt.stt import TranscriptionResult


class STTClient(Protocol):
    def transcribe(self, utterance: Utterance) -> TranscriptionResult:
        ...


class LLMClient(Protocol):
    def run(
        self,
        user_prompt: str,
        *,
        env: EnvironmentContext | None = None,
        extra_context: str | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResponse:
        ...


class TTSClient(Protocol):
    def speak(self, text: str) -> None:
        ...

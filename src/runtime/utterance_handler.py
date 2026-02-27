"""Utterance processing flow for STT -> LLM -> tool dispatch -> TTS."""

from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any, Callable

from contracts.ui_protocol import (
    EVENT_ASSISTANT_REPLY,
    EVENT_ERROR,
    EVENT_TRANSCRIPT,
    STATE_ERROR,
    STATE_IDLE,
    STATE_REPLYING,
    STATE_THINKING,
    STATE_TRANSCRIBING,
)
from llm.types import EnvironmentContext

from .ports import LLMClient, OracleContextClient, SpeechClient, STTClient
from .tool_dispatch import RuntimeToolDispatcher
from .ui import RuntimeUIPublisher

try:
    from llm.fast_path import maybe_fast_path_response
except Exception:  # pragma: no cover - optional import in isolated tests
    maybe_fast_path_response = None


class RuntimeUtteranceHandler:
    """Coordinates processing of a single captured utterance."""

    def __init__(
        self,
        *,
        logger: logging.Logger,
        stt: STTClient,
        assistant_llm: LLMClient | None,
        speech_service: SpeechClient | None,
        oracle_service: OracleContextClient | None,
        dispatcher: RuntimeToolDispatcher,
        ui: RuntimeUIPublisher,
        llm_fast_path_enabled: bool,
        publish_idle_state: Callable[[], None],
    ) -> None:
        self._logger = logger
        self._stt = stt
        self._assistant_llm = assistant_llm
        self._speech_service = speech_service
        self._oracle_service = oracle_service
        self._dispatcher = dispatcher
        self._ui = ui
        self._llm_fast_path_enabled = llm_fast_path_enabled
        self._publish_idle_state = publish_idle_state

    async def process_utterance(self, frame: Any) -> None:
        stage = "Transcription"
        try:
            started_at = time.perf_counter()
            result = self._stt.transcribe(frame.utterance)
            frame.stt_duration_seconds = time.perf_counter() - started_at
            frame.transcript_text = result.text.strip()
            frame.language = result.language
            frame.confidence = result.confidence
            if not frame.transcript_text:
                self._ui.publish_state(STATE_IDLE, message="No speech detected")
                return

            self._ui.publish(
                EVENT_TRANSCRIPT,
                state=STATE_TRANSCRIBING,
                text=frame.transcript_text,
                language=frame.language,
                confidence=frame.confidence,
            )

            if self._assistant_llm is not None:
                stage = "LLM processing"
                self._ui.publish_state(STATE_THINKING, message="Generating reply")
                llm_response: dict[str, object] | None = None

                if self._llm_fast_path_enabled and callable(maybe_fast_path_response):
                    started_at = time.perf_counter()
                    llm_response = maybe_fast_path_response(frame.transcript_text)
                    frame.fast_path_duration_seconds = time.perf_counter() - started_at
                    frame.fast_path_used = llm_response is not None

                if llm_response is None:
                    env = self._build_llm_environment_context()
                    started_at = time.perf_counter()
                    llm_response = self._assistant_llm.run(frame.transcript_text, env=env)
                    frame.llm_duration_seconds = time.perf_counter() - started_at

                frame.assistant_text = str(llm_response.get("assistant_text", "")).strip()
                raw_tool = llm_response.get("tool_call")
                frame.tool_call = raw_tool if isinstance(raw_tool, dict) else None

            stage = "Tool dispatch"
            if frame.tool_call is not None:
                frame.assistant_text = self._dispatcher.handle_tool_call(
                    frame.tool_call,
                    frame.assistant_text,
                ).strip()

            if frame.assistant_text:
                stage = "TTS playback"
                self._ui.publish_state(STATE_REPLYING, message="Delivering reply")
                self._ui.publish(EVENT_ASSISTANT_REPLY, text=frame.assistant_text)
                if self._speech_service is not None:
                    started_at = time.perf_counter()
                    self._speech_service.speak(frame.assistant_text)
                    frame.tts_duration_seconds = time.perf_counter() - started_at
        except Exception as error:
            self._logger.error("%s failed: %s", stage, error)
            self._ui.publish(
                EVENT_ERROR,
                state=STATE_ERROR,
                message=f"{stage} failed: {error}",
            )
        finally:
            total = time.perf_counter() - frame.started_at
            fmt = lambda value: "n/a" if value is None else str(round(value * 1000))
            self._logger.info(
                "Pipecat utterance metrics: total_ms=%d stt_ms=%s llm_ms=%s tts_ms=%s fast_path=%s fast_path_ms=%s transcript_chars=%d",
                round(total * 1000),
                fmt(frame.stt_duration_seconds),
                fmt(frame.llm_duration_seconds),
                fmt(frame.tts_duration_seconds),
                frame.fast_path_used,
                fmt(frame.fast_path_duration_seconds),
                len(frame.transcript_text),
            )
            self._publish_idle_state()

    def _build_llm_environment_context(self) -> EnvironmentContext:
        now_local = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        payload: dict[str, object] = {}
        if self._oracle_service is not None:
            try:
                payload = self._oracle_service.build_environment_payload()
            except Exception as error:
                self._logger.warning("Failed to collect oracle context: %s", error)
        return EnvironmentContext(
            now_local=str(payload.get("now_local") or now_local),
            light_level_lux=payload.get("light_level_lux"),
            air_quality=payload.get("air_quality"),
            upcoming_events=payload.get("upcoming_events"),
        )

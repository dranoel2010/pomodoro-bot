"""Utterance pipeline that runs STT, LLM, tool dispatch, and TTS."""

from __future__ import annotations

import logging
import time
from typing import Callable

from llm.types import EnvironmentContext, StructuredResponse, ToolCall
from stt.events import Utterance
from stt.stt import STTError
from tts.engine import TTSError
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

from .ui import RuntimeUIPublisher
from .contracts import LLMClient, STTClient, TTSClient

try:
    from llm.fast_path import maybe_fast_path_response
except Exception:  # pragma: no cover - optional import in isolated tests
    maybe_fast_path_response = None


def process_utterance(
    utterance: Utterance,
    *,
    stt: STTClient,
    assistant_llm: LLMClient | None,
    speech_service: TTSClient | None,
    logger: logging.Logger,
    ui: RuntimeUIPublisher,
    build_llm_environment_context: Callable[[], EnvironmentContext],
    handle_tool_call: Callable[[ToolCall, str], str],
    publish_idle_state: Callable[[], None],
    llm_fast_path_enabled: bool = True,
) -> None:
    pipeline_started_at = time.perf_counter()
    stt_duration_seconds: float | None = None
    llm_duration_seconds: float | None = None
    tts_duration_seconds: float | None = None
    fast_path_duration_seconds: float | None = None
    fast_path_used = False
    transcript_text = ""

    logger.info("Transcribing captured utterance...")
    try:
        stt_started_at = time.perf_counter()
        result = stt.transcribe(utterance)
        stt_duration_seconds = time.perf_counter() - stt_started_at
        transcript_text = result.text.strip()
        if not transcript_text:
            logger.info("No speech detected in captured utterance.")
            ui.publish_state(STATE_IDLE, message="No speech detected")
            return

        logger.info(
            "Transcription result: text=%r language=%s confidence=%s",
            transcript_text,
            result.language,
            f"{result.confidence:.2f}" if result.confidence is not None else "n/a",
        )
        ui.publish(
            EVENT_TRANSCRIPT,
            state=STATE_TRANSCRIBING,
            text=transcript_text,
            language=result.language,
            confidence=result.confidence,
        )

        if assistant_llm is None:
            publish_idle_state()
            return

        ui.publish_state(STATE_THINKING, message="Generating reply")
        llm_response: StructuredResponse | None = None
        if llm_fast_path_enabled and callable(maybe_fast_path_response):
            fast_path_started_at = time.perf_counter()
            llm_response = maybe_fast_path_response(transcript_text)
            fast_path_duration_seconds = time.perf_counter() - fast_path_started_at
            if llm_response is not None:
                fast_path_used = True
                fast_tool_name = None
                fast_tool_call = llm_response.get("tool_call")
                if fast_tool_call is not None:
                    fast_tool_name = fast_tool_call.get("name")
                logger.info(
                    "LLM fast-path hit: duration_ms=%d tool=%s",
                    round(fast_path_duration_seconds * 1000),
                    fast_tool_name,
                )

        if llm_response is None:
            env_context = build_llm_environment_context()
            llm_started_at = time.perf_counter()
            llm_response = assistant_llm.run(transcript_text, env=env_context)
            llm_duration_seconds = time.perf_counter() - llm_started_at

        assistant_text = llm_response["assistant_text"].strip()
        tool_call = llm_response.get("tool_call")
        if tool_call is not None:
            assistant_text = handle_tool_call(tool_call, assistant_text).strip()

        if assistant_text:
            logger.info("Assistant reply ready: %r", assistant_text)
            ui.publish_state(STATE_REPLYING, message="Delivering reply")
            ui.publish(EVENT_ASSISTANT_REPLY, text=assistant_text)
            if speech_service is not None:
                tts_started_at = time.perf_counter()
                speech_service.speak(assistant_text)
                tts_duration_seconds = time.perf_counter() - tts_started_at
        publish_idle_state()
    except (STTError, TTSError) as error:
        prefix = "Transcription failed" if isinstance(error, STTError) else "TTS playback failed"
        _publish_error(prefix, error, logger=logger, ui=ui, publish_idle_state=publish_idle_state)
    except Exception as error:
        _publish_error(
            "LLM processing failed",
            error,
            logger=logger,
            ui=ui,
            publish_idle_state=publish_idle_state,
        )
    finally:
        total_duration_seconds = time.perf_counter() - pipeline_started_at
        logger.info(
            "Utterance pipeline metrics: total_ms=%d stt_ms=%s llm_ms=%s tts_ms=%s fast_path=%s fast_path_ms=%s transcript_chars=%d",
            round(total_duration_seconds * 1000),
            _fmt_duration_ms(stt_duration_seconds),
            _fmt_duration_ms(llm_duration_seconds),
            _fmt_duration_ms(tts_duration_seconds),
            fast_path_used,
            _fmt_duration_ms(fast_path_duration_seconds),
            len(transcript_text),
        )


def _publish_error(
    prefix: str,
    error: Exception,
    *,
    logger: logging.Logger,
    ui: RuntimeUIPublisher,
    publish_idle_state: Callable[[], None],
) -> None:
    logger.error("%s: %s", prefix, error)
    ui.publish(
        EVENT_ERROR,
        state=STATE_ERROR,
        message=f"{prefix}: {error}",
    )
    publish_idle_state()


def _fmt_duration_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return str(round(value * 1000))

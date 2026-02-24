"""Utterance pipeline that runs STT, LLM, tool dispatch, and TTS."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from llm import EnvironmentContext, PomodoroAssistantLLM
from stt import FasterWhisperSTT, STTError, Utterance
from tts import SpeechService, TTSError
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


def process_utterance(
    utterance: Utterance,
    *,
    stt: FasterWhisperSTT,
    assistant_llm: Optional[PomodoroAssistantLLM],
    speech_service: Optional[SpeechService],
    logger: logging.Logger,
    ui: RuntimeUIPublisher,
    build_llm_environment_context: Callable[[], EnvironmentContext],
    handle_tool_call: Callable[[dict[str, object], str], str],
    publish_idle_state: Callable[[], None],
) -> None:
    logger.info("Transcribing captured utterance...")
    try:
        result = stt.transcribe(utterance)
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
        env_context = build_llm_environment_context()
        llm_response = assistant_llm.run(transcript_text, env=env_context)
        assistant_text = llm_response["assistant_text"].strip()
        tool_call = llm_response.get("tool_call")
        if isinstance(tool_call, dict):
            assistant_text = handle_tool_call(tool_call, assistant_text).strip()

        if assistant_text:
            logger.info("Assistant reply ready: %r", assistant_text)
            ui.publish_state(STATE_REPLYING, message="Delivering reply")
            ui.publish(EVENT_ASSISTANT_REPLY, text=assistant_text)
            if speech_service is not None:
                speech_service.speak(assistant_text)
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

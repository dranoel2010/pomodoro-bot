"""Utterance pipeline that runs STT, LLM, tool dispatch, and TTS."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from llm import EnvironmentContext, PomodoroAssistantLLM
from stt import FasterWhisperSTT, STTError
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


@dataclass(frozen=True)
class UtteranceDependencies:
    """Dependencies required to process one captured utterance."""
    stt: FasterWhisperSTT
    assistant_llm: Optional[PomodoroAssistantLLM]
    speech_service: Optional[SpeechService]
    logger: logging.Logger
    ui: RuntimeUIPublisher
    build_llm_environment_context: Callable[[], EnvironmentContext]
    handle_tool_call: Callable[[dict[str, object], str], str]
    publish_idle_state: Callable[[], None]


class UtteranceProcessor:
    """Executes STT, optional LLM inference, tool dispatch, and optional TTS."""
    def __init__(self, dependencies: UtteranceDependencies):
        self._dependencies = dependencies

    def process(self, utterance: object) -> None:
        deps = self._dependencies
        logger = deps.logger
        ui = deps.ui

        logger.info("Transcribing captured utterance...")
        try:
            result = deps.stt.transcribe(utterance)
            if not result.text:
                logger.info("No speech detected in captured utterance.")
                ui.publish_state(STATE_IDLE, message="No speech detected")
                return

            logger.info(
                "Transcription result: text=%r language=%s confidence=%s",
                result.text,
                result.language,
                f"{result.confidence:.2f}" if result.confidence is not None else "n/a",
            )
            ui.publish(
                EVENT_TRANSCRIPT,
                state=STATE_TRANSCRIBING,
                text=result.text,
                language=result.language,
                confidence=result.confidence,
            )

            if deps.assistant_llm is None:
                deps.publish_idle_state()
                return

            ui.publish_state(STATE_THINKING, message="Generating reply")
            env_context = deps.build_llm_environment_context()
            llm_response = deps.assistant_llm.run(result.text, env=env_context)
            assistant_text = llm_response["assistant_text"].strip()
            tool_call = llm_response.get("tool_call")
            if isinstance(tool_call, dict):
                assistant_text = deps.handle_tool_call(tool_call, assistant_text).strip()

            if assistant_text:
                logger.info("Assistant reply ready: %r", assistant_text)
                ui.publish_state(STATE_REPLYING, message="Delivering reply")
                ui.publish(
                    EVENT_ASSISTANT_REPLY,
                    text=assistant_text,
                )
            if deps.speech_service and assistant_text:
                deps.speech_service.speak(assistant_text)
            deps.publish_idle_state()
        except TTSError as error:
            logger.error(f"TTS playback failed: {error}")
            ui.publish(
                EVENT_ERROR,
                state=STATE_ERROR,
                message=f"TTS playback failed: {error}",
            )
            deps.publish_idle_state()
        except STTError as error:
            logger.error(f"Transcription failed: {error}")
            ui.publish(
                EVENT_ERROR,
                state=STATE_ERROR,
                message=f"Transcription failed: {error}",
            )
            deps.publish_idle_state()
        except Exception as error:
            logger.error(f"LLM processing failed: {error}")
            ui.publish(
                EVENT_ERROR,
                state=STATE_ERROR,
                message=f"LLM processing failed: {error}",
            )
            deps.publish_idle_state()

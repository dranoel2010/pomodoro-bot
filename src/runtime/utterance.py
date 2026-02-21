from __future__ import annotations

import logging
from typing import Callable, Optional

from llm import EnvironmentContext, PomodoroAssistantLLM
from stt import FasterWhisperSTT, STTError
from tts import SpeechService, TTSError

from .ui import RuntimeUIPublisher


def process_utterance(
    *,
    utterance,
    stt: FasterWhisperSTT,
    assistant_llm: Optional[PomodoroAssistantLLM],
    speech_service: Optional[SpeechService],
    logger: logging.Logger,
    ui: RuntimeUIPublisher,
    build_llm_environment_context: Callable[[], EnvironmentContext],
    handle_tool_call: Callable[[dict[str, object], str], str],
    publish_idle_state: Callable[[], None],
) -> None:
    print("  ⏳ Transcribing...\n", end="", flush=True)
    try:
        result = stt.transcribe(utterance)
        if not result.text:
            print("\r  ⚠️  No speech detected\n")
            ui.publish_state("idle", message="No speech detected")
            return

        confidence_str = f" (confidence: {result.confidence:.0%})" if result.confidence else ""
        print(f'\r  💬 "{result.text}"{confidence_str}\n')
        ui.publish(
            "transcript",
            state="transcribing",
            text=result.text,
            language=result.language,
            confidence=result.confidence,
        )

        if not assistant_llm:
            publish_idle_state()
            return

        ui.publish_state("thinking", message="Generating reply")
        env_context = build_llm_environment_context()
        llm_response = assistant_llm.run(result.text, env=env_context)
        assistant_text = llm_response["assistant_text"].strip()
        tool_call = llm_response.get("tool_call")
        if isinstance(tool_call, dict):
            assistant_text = handle_tool_call(tool_call, assistant_text).strip()

        if assistant_text:
            print(f'  🤖 "{assistant_text}"\n')
            ui.publish_state("replying", message="Delivering reply")
            ui.publish(
                "assistant_reply",
                text=assistant_text,
            )
        if speech_service and assistant_text:
            speech_service.speak(assistant_text)
        publish_idle_state()
    except TTSError as error:
        logger.error(f"TTS playback failed: {error}")
        ui.publish(
            "error",
            state="error",
            message=f"TTS playback failed: {error}",
        )
        publish_idle_state()
    except STTError as error:
        logger.error(f"Transcription failed: {error}")
        ui.publish(
            "error",
            state="error",
            message=f"Transcription failed: {error}",
        )
        publish_idle_state()
    except Exception as error:
        logger.error(f"LLM processing failed: {error}")
        ui.publish(
            "error",
            state="error",
            message=f"LLM processing failed: {error}",
        )
        publish_idle_state()

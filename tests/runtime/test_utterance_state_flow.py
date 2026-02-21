import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Import runtime.utterance without executing src/runtime/__init__.py.
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg


def _build_llm_stub():
    module = types.ModuleType("llm")

    class EnvironmentContext:  # pragma: no cover - type placeholder
        pass

    class PomodoroAssistantLLM:  # pragma: no cover - type placeholder
        pass

    module.EnvironmentContext = EnvironmentContext
    module.PomodoroAssistantLLM = PomodoroAssistantLLM
    return module


def _build_stt_stub():
    module = types.ModuleType("stt")

    class STTError(Exception):
        pass

    class FasterWhisperSTT:  # pragma: no cover - type placeholder
        pass

    module.STTError = STTError
    module.FasterWhisperSTT = FasterWhisperSTT
    return module


def _build_tts_stub():
    module = types.ModuleType("tts")

    class TTSError(Exception):
        pass

    class SpeechService:  # pragma: no cover - type placeholder
        pass

    module.TTSError = TTSError
    module.SpeechService = SpeechService
    return module


with patch.dict(
    sys.modules,
    {
        "llm": _build_llm_stub(),
        "stt": _build_stt_stub(),
        "tts": _build_tts_stub(),
    },
):
    from runtime.utterance import process_utterance


class _TranscriptionResultStub:
    def __init__(self, *, text: str, language: str, confidence: float | None):
        self.text = text
        self.language = language
        self.confidence = confidence


class _STTStub:
    def __init__(self, result: _TranscriptionResultStub):
        self._result = result

    def transcribe(self, utterance):
        return self._result


class _AssistantLLMStub:
    def __init__(self, response: dict[str, object]):
        self._response = response

    def run(self, prompt: str, env):
        return dict(self._response)


class _UIServerStub:
    def __init__(self):
        self.events: list[tuple[str, dict[str, object]]] = []
        self.states: list[tuple[str, str | None, dict[str, object]]] = []
        self.trace: list[tuple[str, str]] = []

    def publish(self, event_type: str, **payload):
        self.events.append((event_type, payload))
        self.trace.append(("event", event_type))

    def publish_state(self, state: str, *, message=None, **payload):
        self.states.append((state, message, payload))
        self.trace.append(("state", state))


class UtteranceStateFlowTests(unittest.TestCase):
    def test_process_utterance_uses_state_update_for_replying(self) -> None:
        ui = _UIServerStub()
        idle_calls: list[str] = []

        process_utterance(
            utterance=object(),
            stt=_STTStub(
                _TranscriptionResultStub(
                    text="stop timer",
                    language="en",
                    confidence=0.9,
                )
            ),
            assistant_llm=_AssistantLLMStub(
                {"assistant_text": "Timer stopped.", "tool_call": None}
            ),
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            build_llm_environment_context=lambda: object(),
            handle_tool_call=lambda tool_call, assistant_text: assistant_text,
            publish_idle_state=lambda: idle_calls.append("idle"),
        )

        self.assertIn(("replying", "Delivering reply", {}), ui.states)

        assistant_events = [payload for kind, payload in ui.events if kind == "assistant_reply"]
        self.assertEqual(1, len(assistant_events))
        self.assertEqual("Timer stopped.", assistant_events[0]["text"])
        self.assertNotIn("state", assistant_events[0])
        self.assertEqual(["idle"], idle_calls)

        self.assertLess(
            ui.trace.index(("state", "replying")),
            ui.trace.index(("event", "assistant_reply")),
        )


if __name__ == "__main__":
    unittest.main()

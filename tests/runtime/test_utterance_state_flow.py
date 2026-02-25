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


def _build_llm_stub_modules():
    package = types.ModuleType("llm")
    package.__path__ = []  # type: ignore[attr-defined]
    service_module = types.ModuleType("llm.service")
    types_module = types.ModuleType("llm.types")

    class EnvironmentContext:  # pragma: no cover - type placeholder
        pass

    class PomodoroAssistantLLM:  # pragma: no cover - type placeholder
        pass

    types_module.EnvironmentContext = EnvironmentContext
    service_module.PomodoroAssistantLLM = PomodoroAssistantLLM
    package.service = service_module
    package.types = types_module
    return {
        "llm": package,
        "llm.service": service_module,
        "llm.types": types_module,
    }


def _build_stt_stub_modules():
    package = types.ModuleType("stt")
    package.__path__ = []  # type: ignore[attr-defined]
    events_module = types.ModuleType("stt.events")
    stt_module = types.ModuleType("stt.stt")

    class STTError(Exception):
        pass

    class FasterWhisperSTT:  # pragma: no cover - type placeholder
        pass

    class Utterance:  # pragma: no cover - type placeholder
        pass

    stt_module.STTError = STTError
    stt_module.FasterWhisperSTT = FasterWhisperSTT
    events_module.Utterance = Utterance
    package.stt = stt_module
    package.events = events_module
    return {
        "stt": package,
        "stt.stt": stt_module,
        "stt.events": events_module,
    }


def _build_tts_stub_modules():
    package = types.ModuleType("tts")
    package.__path__ = []  # type: ignore[attr-defined]
    engine_module = types.ModuleType("tts.engine")
    service_module = types.ModuleType("tts.service")

    class TTSError(Exception):
        pass

    class SpeechService:  # pragma: no cover - type placeholder
        pass

    engine_module.TTSError = TTSError
    service_module.SpeechService = SpeechService
    package.engine = engine_module
    package.service = service_module
    return {
        "tts": package,
        "tts.engine": engine_module,
        "tts.service": service_module,
    }


with patch.dict(
    sys.modules,
    {
        **_build_llm_stub_modules(),
        **_build_stt_stub_modules(),
        **_build_tts_stub_modules(),
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
            object(),
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
            llm_fast_path_enabled=False,
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

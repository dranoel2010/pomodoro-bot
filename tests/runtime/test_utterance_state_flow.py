from __future__ import annotations

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

    class PipelineMetrics:  # pragma: no cover - type placeholder
        def __init__(self, **kwargs):  # type: ignore[override]
            for k, v in kwargs.items():
                object.__setattr__(self, k, v)

        def to_json(self) -> str:
            import json
            return json.dumps({"event": "pipeline_metrics"})

    types_module.EnvironmentContext = EnvironmentContext
    types_module.StructuredResponse = dict
    types_module.ToolCall = dict
    types_module.JSONObject = dict
    types_module.PipelineMetrics = PipelineMetrics
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
    stt_module = types.ModuleType("stt.transcription")

    class STTError(Exception):
        pass

    class FasterWhisperSTT:  # pragma: no cover - type placeholder
        pass

    class Utterance:  # pragma: no cover - type placeholder
        pass

    stt_module.STTError = STTError
    stt_module.FasterWhisperSTT = FasterWhisperSTT
    events_module.Utterance = Utterance
    package.transcription = stt_module
    package.events = events_module
    return {
        "stt": package,
        "stt.transcription": stt_module,
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

# src/ is on sys.path via pyproject.toml [tool.pytest.ini_options] pythonpath = ["src"]
from contracts.ui_protocol import EVENT_ASSISTANT_REPLY, STATE_REPLYING


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
        self.run_call_count = 0

    def run(self, prompt: str, *, env=None, extra_context=None, max_tokens=None):
        self.run_call_count += 1
        return dict(self._response)

    @property
    def last_tokens(self) -> int:
        return 0


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

        self.assertIn((STATE_REPLYING, "Delivering reply", {}), ui.states)

        assistant_events = [payload for kind, payload in ui.events if kind == EVENT_ASSISTANT_REPLY]
        self.assertEqual(1, len(assistant_events))
        self.assertEqual("Timer stopped.", assistant_events[0]["text"])
        self.assertNotIn("state", assistant_events[0])
        self.assertEqual(["idle"], idle_calls)

        self.assertLess(
            ui.trace.index(("state", STATE_REPLYING)),
            ui.trace.index(("event", EVENT_ASSISTANT_REPLY)),
        )

    def test_process_utterance_fast_path_bypasses_llm(self) -> None:
        ui = _UIServerStub()
        idle_calls: list[str] = []
        llm_stub = _AssistantLLMStub(
            {"assistant_text": "LLM was called unexpectedly", "tool_call": None}
        )

        _fast_path_response = {
            "assistant_text": "Timer gestoppt.",
            "tool_call": {"name": "stop_timer", "arguments": {}},
        }

        # patch.dict on __globals__ is required: the outer patch.dict(sys.modules, ...)
        # removes runtime.utterance on exit, so standard patch("runtime.utterance.maybe_fast_path_response")
        # would target a stale module instance. Patching the globals dict directly avoids this.
        with patch.dict(
            process_utterance.__globals__,
            {"maybe_fast_path_response": lambda _: _fast_path_response},
        ):
            process_utterance(
                object(),
                stt=_STTStub(
                    _TranscriptionResultStub(
                        text="Stopp den Timer",
                        language="de",
                        confidence=0.95,
                    )
                ),
                assistant_llm=llm_stub,
                speech_service=None,
                logger=logging.getLogger("test"),
                ui=ui,
                build_llm_environment_context=lambda: object(),
                handle_tool_call=lambda tool_call, assistant_text: assistant_text,
                publish_idle_state=lambda: idle_calls.append("idle"),
                llm_fast_path_enabled=True,
            )

        # Fast-path must bypass LLM entirely
        self.assertEqual(
            0,
            llm_stub.run_call_count,
            "LLM must not be called when fast-path handles the request",
        )
        self.assertIn((STATE_REPLYING, "Delivering reply", {}), ui.states)
        assistant_events = [
            payload for kind, payload in ui.events if kind == EVENT_ASSISTANT_REPLY
        ]
        self.assertEqual(1, len(assistant_events))
        self.assertEqual("Timer gestoppt.", assistant_events[0]["text"])
        self.assertLess(
            ui.trace.index(("state", STATE_REPLYING)),
            ui.trace.index(("event", EVENT_ASSISTANT_REPLY)),
        )
        self.assertEqual(["idle"], idle_calls)


class TellJokeFastPathMetricsTests(unittest.TestCase):
    """Verify tell_joke fast-path produces zeroed LLM pipeline metrics (AC #4)."""

    def test_tell_joke_fast_path_zeroes_llm_ms_and_tokens(self) -> None:
        ui = _UIServerStub()
        captured: list[dict] = []

        def _capturing_metrics(**kwargs: object) -> object:
            captured.append(dict(kwargs))

            class _Stub:
                def to_json(self) -> str:
                    return '{"event":"pipeline_metrics"}'

            return _Stub()

        tell_joke_response = {
            "assistant_text": "Anfrage verarbeitet.",
            "tool_call": {"name": "tell_joke", "arguments": {}},
        }

        with patch.dict(
            process_utterance.__globals__,
            {
                "maybe_fast_path_response": lambda _: tell_joke_response,
                "PipelineMetrics": _capturing_metrics,
            },
        ):
            process_utterance(
                object(),
                stt=_STTStub(
                    _TranscriptionResultStub(
                        text="Erzähl mir einen Witz",
                        language="de",
                        confidence=0.9,
                    )
                ),
                assistant_llm=_AssistantLLMStub(
                    {"assistant_text": "LLM should not be called", "tool_call": None}
                ),
                speech_service=None,
                logger=logging.getLogger("test"),
                ui=ui,
                build_llm_environment_context=lambda: object(),
                handle_tool_call=lambda tool_call, assistant_text: "Warum können Geister so schlecht lügen?",
                publish_idle_state=lambda: None,
                llm_fast_path_enabled=True,
            )

        self.assertEqual(1, len(captured))
        self.assertEqual(0, captured[0]["llm_ms"], "Fast-path must zero llm_ms — no LLM inference")
        self.assertEqual(0, captured[0]["tokens"], "Fast-path must zero tokens — no LLM inference")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Bootstrap runtime package (same pattern as test_utterance_state_flow.py)
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg

# Import worker error types BEFORE the patch.dict context.
# runtime.workers.core has no heavy native deps (only stdlib + contracts.ipc).
# By importing here, runtime.workers.core is added to sys.modules BEFORE patch.dict,
# so patch.dict will NOT remove it when the with-block exits.
from runtime.workers.core import WorkerCallTimeoutError, WorkerClosedError, WorkerCrashError, WorkerTaskError


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


class _TranscriptionResultStub:
    def __init__(self, text: str = "stopp den timer", language: str = "de", confidence: float | None = 0.9):
        self.text = text
        self.language = language
        self.confidence = confidence


class _STTStub:
    """Returns a successful transcription result or raises a given worker error."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    def transcribe(self, utterance: object) -> _TranscriptionResultStub:
        if self._error is not None:
            raise self._error
        return _TranscriptionResultStub()


class _LLMStub:
    """Returns a fixed LLM response or raises a given worker error."""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        response: dict | None = None,
    ) -> None:
        self._error = error
        self._response = response or {"assistant_text": "Ich habe das verstanden.", "tool_call": None}

    def run(self, prompt: str, *, env: object = None, extra_context: object = None, max_tokens: object = None) -> dict:
        if self._error is not None:
            raise self._error
        return dict(self._response)

    @property
    def last_tokens(self) -> int:
        return 0


class _TTSStub:
    """Speaks silently or raises a given worker error."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    def speak(self, text: str) -> None:
        if self._error is not None:
            raise self._error


class _UIStub:
    def __init__(self) -> None:
        self.error_events: list[str] = []

    def publish(self, event_type: str, **payload: object) -> None:
        if event_type == "error":
            self.error_events.append(event_type)

    def publish_state(self, state: str, *, message: object = None, **payload: object) -> None:
        pass


def _find_worker_event(info_call_args: list[str], event: str) -> dict | None:
    """Return the first dict found in info calls where data["event"] == event."""
    for msg in info_call_args:
        try:
            data = json.loads(msg)
            if isinstance(data, dict) and data.get("event") == event:
                return data
        except (ValueError, TypeError):
            pass
    return None


class WorkerErrorLoggingTests(unittest.TestCase):
    def test_worker_call_timeout_logs_structured_worker_timeout_event(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        idle_calls: list[str] = []
        ui_stub = _UIStub()

        process_utterance(
            object(),
            stt=_STTStub(error=WorkerCallTimeoutError("STT worker timed out.")),
            assistant_llm=_LLMStub(),
            speech_service=None,
            logger=mock_logger,
            ui=ui_stub,
            build_llm_environment_context=lambda: object(),
            handle_tool_call=lambda tool_call, assistant_text: assistant_text,
            publish_idle_state=lambda: idle_calls.append("idle"),
            llm_fast_path_enabled=False,
        )

        info_call_args = [call.args[0] for call in mock_logger.info.call_args_list if call.args]
        event_data = _find_worker_event(info_call_args, "worker_timeout")
        self.assertIsNotNone(event_data, "Expected structured log entry with event='worker_timeout'")
        self.assertEqual("STT worker timed out.", event_data["message"])
        self.assertEqual(["idle"], idle_calls)
        self.assertEqual([], ui_stub.error_events, "Worker errors must not publish UI error events")

    def test_worker_crash_logs_structured_worker_crash_event(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        idle_calls: list[str] = []
        ui_stub = _UIStub()

        process_utterance(
            object(),
            stt=_STTStub(),
            assistant_llm=_LLMStub(error=WorkerCrashError("LLM worker crashed.")),
            speech_service=None,
            logger=mock_logger,
            ui=ui_stub,
            build_llm_environment_context=lambda: object(),
            handle_tool_call=lambda tool_call, assistant_text: assistant_text,
            publish_idle_state=lambda: idle_calls.append("idle"),
            llm_fast_path_enabled=False,
        )

        info_call_args = [call.args[0] for call in mock_logger.info.call_args_list if call.args]
        event_data = _find_worker_event(info_call_args, "worker_crash")
        self.assertIsNotNone(event_data, "Expected structured log entry with event='worker_crash'")
        self.assertEqual("LLM worker crashed.", event_data["message"])
        self.assertEqual(["idle"], idle_calls)
        self.assertEqual([], ui_stub.error_events, "Worker errors must not publish UI error events")

    def test_worker_task_error_logs_structured_worker_task_error_event(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        idle_calls: list[str] = []
        ui_stub = _UIStub()

        process_utterance(
            object(),
            stt=_STTStub(),
            assistant_llm=_LLMStub(),
            speech_service=_TTSStub(error=WorkerTaskError("TTS task failed: SomeTTSError")),
            logger=mock_logger,
            ui=ui_stub,
            build_llm_environment_context=lambda: object(),
            handle_tool_call=lambda tool_call, assistant_text: assistant_text,
            publish_idle_state=lambda: idle_calls.append("idle"),
            llm_fast_path_enabled=False,
        )

        info_call_args = [call.args[0] for call in mock_logger.info.call_args_list if call.args]
        event_data = _find_worker_event(info_call_args, "worker_task_error")
        self.assertIsNotNone(event_data, "Expected structured log entry with event='worker_task_error'")
        self.assertEqual("TTS task failed: SomeTTSError", event_data["message"])
        self.assertEqual(["idle"], idle_calls)
        self.assertEqual([], ui_stub.error_events, "Worker errors must not publish UI error events")

    def test_worker_error_main_process_does_not_crash(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        ui_stub = _UIStub()

        # Must not raise — worker errors are caught and logged, main process survives
        process_utterance(
            object(),
            stt=_STTStub(),
            assistant_llm=_LLMStub(error=WorkerCrashError("LLM worker crashed.")),
            speech_service=None,
            logger=mock_logger,
            ui=ui_stub,
            build_llm_environment_context=lambda: object(),
            handle_tool_call=lambda tool_call, assistant_text: assistant_text,
            publish_idle_state=lambda: None,
            llm_fast_path_enabled=False,
        )
        self.assertEqual([], ui_stub.error_events, "Worker errors must not publish UI error events")

    def test_worker_error_log_is_valid_json_with_required_fields(self) -> None:
        mock_logger = MagicMock(spec=logging.Logger)
        ui_stub = _UIStub()

        process_utterance(
            object(),
            stt=_STTStub(error=WorkerCallTimeoutError("STT worker timed out.")),
            assistant_llm=_LLMStub(),
            speech_service=None,
            logger=mock_logger,
            ui=ui_stub,
            build_llm_environment_context=lambda: object(),
            handle_tool_call=lambda tool_call, assistant_text: assistant_text,
            publish_idle_state=lambda: None,
            llm_fast_path_enabled=False,
        )

        info_call_args = [call.args[0] for call in mock_logger.info.call_args_list if call.args]
        event_data = _find_worker_event(info_call_args, "worker_timeout")
        self.assertIsNotNone(event_data, "No valid JSON worker error entry found in logger.info calls")
        self.assertIn("event", event_data)
        self.assertIn("message", event_data)
        self.assertEqual([], ui_stub.error_events, "Worker errors must not publish UI error events")

    def test_worker_base_error_logs_structured_worker_error_event(self) -> None:
        """WorkerClosedError (WorkerError subtype not in the three specific handlers) is caught and
        logged via the base WorkerError handler — not swallowed by except Exception."""
        mock_logger = MagicMock(spec=logging.Logger)
        idle_calls: list[str] = []
        ui_stub = _UIStub()

        process_utterance(
            object(),
            stt=_STTStub(error=WorkerClosedError("STT worker closed.")),
            assistant_llm=_LLMStub(),
            speech_service=None,
            logger=mock_logger,
            ui=ui_stub,
            build_llm_environment_context=lambda: object(),
            handle_tool_call=lambda tool_call, assistant_text: assistant_text,
            publish_idle_state=lambda: idle_calls.append("idle"),
            llm_fast_path_enabled=False,
        )

        info_call_args = [call.args[0] for call in mock_logger.info.call_args_list if call.args]
        event_data = _find_worker_event(info_call_args, "worker_error")
        self.assertIsNotNone(event_data, "Expected structured log entry with event='worker_error'")
        self.assertIn("message", event_data)
        self.assertEqual(["idle"], idle_calls)
        self.assertEqual([], ui_stub.error_events, "Worker errors must not publish UI error events")


if __name__ == "__main__":
    unittest.main()

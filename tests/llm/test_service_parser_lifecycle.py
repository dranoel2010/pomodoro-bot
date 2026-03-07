from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Import llm modules without executing src/llm/__init__.py.
_LLM_DIR = Path(__file__).resolve().parents[2] / "src" / "llm"
if "llm" not in sys.modules:
    _pkg = types.ModuleType("llm")
    _pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _pkg

from llm.config import LLMConfig
from llm.service import PomodoroAssistantLLM


class _BackendStub:
    responses: list[str] = []

    def __init__(self, config):
        del config
        self.last_usage = None
        self.last_finish_reason = "stop"
        self.last_prompt_tokens = None
        self.last_completion_tokens = None
        self.last_total_tokens = None

    def complete(self, messages, max_tokens):
        del messages, max_tokens
        if not self.responses:
            raise AssertionError("Backend stub ran out of responses.")
        return self.responses.pop(0)


def _build_config(tmp_root: Path) -> LLMConfig:
    model_path = tmp_root / "dummy.gguf"
    model_path.write_bytes(b"dummy")
    return LLMConfig(model_path=str(model_path))


class ServiceParserLifecycleTests(unittest.TestCase):
    def test_service_reuses_parser_state_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _build_config(Path(tmp))
            _BackendStub.responses = [
                (
                    '{"assistant_text":"",'
                    '"tool_call":{"name":"start_pomodoro_session","arguments":{"focus_topic":"Code Review"}}}'
                ),
                (
                    '{"assistant_text":"",'
                    '"tool_call":{"name":"start_pomodoro_session","arguments":{}}}'
                ),
            ]

            with patch("llm.service.LlamaBackend", _BackendStub):
                service = PomodoroAssistantLLM(config)
                first = service.run("Starte Pomodoro fuer Code Review")
                second = service.run("Starte Pomodoro")

        first_tool_call = first.get("tool_call")
        second_tool_call = second.get("tool_call")
        self.assertIsNotNone(first_tool_call)
        self.assertIsNotNone(second_tool_call)
        if first_tool_call is None or second_tool_call is None:
            self.fail("Expected tool calls in both service responses.")
        self.assertEqual("Code Review", first_tool_call["arguments"]["focus_topic"])
        self.assertEqual("Code Review", second_tool_call["arguments"]["focus_topic"])


if __name__ == "__main__":
    unittest.main()

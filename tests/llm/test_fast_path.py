import sys
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

from llm.fast_path import maybe_fast_path_response


class FastPathTests(unittest.TestCase):
    def test_fast_path_infers_timer_tool_call(self) -> None:
        result = maybe_fast_path_response("Starte einen Timer fuer 15 Minuten")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response")

        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")

        self.assertEqual("start_timer", tool_call["name"])
        self.assertEqual("15m", tool_call["arguments"]["duration"])

    def test_fast_path_returns_none_for_non_action_prompt(self) -> None:
        result = maybe_fast_path_response("Wie spaet ist es gerade?")
        self.assertIsNone(result)

    def test_fast_path_uses_parser_public_api(self) -> None:
        class _ParserStub:
            def infer_tool_call_from_prompt(self, user_prompt: str):
                self.prompt = user_prompt
                return {"name": "stop_timer", "arguments": {}}

            def fallback_assistant_text(self, tool_call):
                del tool_call
                return "Timer gestoppt."

        with patch("llm.fast_path.ResponseParser", return_value=_ParserStub()):
            result = maybe_fast_path_response("Stopp den Timer")

        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response")
        self.assertEqual("Timer gestoppt.", result["assistant_text"])
        self.assertEqual("stop_timer", result["tool_call"]["name"])


if __name__ == "__main__":
    unittest.main()

import datetime as dt
import json
import sys
import types
import unittest
from pathlib import Path

# Import llm modules without executing src/llm/__init__.py.
_LLM_DIR = Path(__file__).resolve().parents[2] / "src" / "llm"
if "llm" not in sys.modules:
    _pkg = types.ModuleType("llm")
    _pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _pkg

from llm.parser import ResponseParser
from llm.parser_extractors import extract_datetime_literal
from llm.parser_rules import detect_action


class ParserStateAndHelpersTests(unittest.TestCase):
    def test_focus_topic_memory_reused_for_followup_start(self) -> None:
        parser = ResponseParser()

        parser.parse(
            json.dumps(
                {
                    "assistant_text": "",
                    "tool_call": {
                        "name": "start_pomodoro_session",
                        "arguments": {"focus_topic": "Code Review"},
                    },
                }
            ),
            "Starte eine Pomodoro Sitzung",
        )

        followup = parser.parse(
            json.dumps(
                {
                    "assistant_text": "",
                    "tool_call": {
                        "name": "start_pomodoro_session",
                        "arguments": {},
                    },
                }
            ),
            "Starte pomodoro",
        )

        tool_call = followup["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected normalized tool_call")
        self.assertEqual("start_pomodoro_session", tool_call["name"])
        self.assertEqual("Code Review", tool_call["arguments"]["focus_topic"])

    def test_time_range_memory_reused_for_followup_show_events(self) -> None:
        parser = ResponseParser()

        parser.parse(
            json.dumps(
                {
                    "assistant_text": "",
                    "tool_call": {
                        "name": "show_upcoming_events",
                        "arguments": {"time_range": "morgen"},
                    },
                }
            ),
            "Zeige Termine morgen",
        )

        followup = parser.parse(
            json.dumps(
                {
                    "assistant_text": "",
                    "tool_call": {
                        "name": "show_upcoming_events",
                        "arguments": {},
                    },
                }
            ),
            "Zeig Kalender",
        )

        tool_call = followup["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected normalized tool_call")
        self.assertEqual("show_upcoming_events", tool_call["name"])
        self.assertEqual("morgen", tool_call["arguments"]["time_range"])

    def test_extract_datetime_literal_relative_uses_injected_now(self) -> None:
        fixed_now = dt.datetime(2026, 2, 21, 10, 0, tzinfo=dt.timezone.utc)
        parsed = extract_datetime_literal(
            "Bitte morgen um 9 uhr",
            now_fn=lambda: fixed_now,
        )
        self.assertEqual("2026-02-22T09:00+00:00", parsed)

    def test_detect_action_prefers_last_match(self) -> None:
        action = detect_action("Starte den Timer und stop ihn dann.")
        self.assertEqual("stop", action)


if __name__ == "__main__":
    unittest.main()

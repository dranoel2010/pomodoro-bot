import json
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# Import llm.parser without executing src/llm/__init__.py, which pulls optional deps.
_LLM_DIR = Path(__file__).resolve().parents[2] / "src" / "llm"
if "llm" not in sys.modules:
    _pkg = types.ModuleType("llm")
    _pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _pkg

from llm.parser import ResponseParser


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        base = datetime(2026, 2, 21, 10, 0, tzinfo=timezone.utc)
        if tz is not None:
            return base.astimezone(tz)
        return base


class ResponseParserCharacterizationTests(unittest.TestCase):
    def test_valid_json_preserved(self) -> None:
        parser = ResponseParser()
        content = json.dumps(
            {
                "assistant_text": "Alles klar",
                "tool_call": {"name": "start_timer", "arguments": {"duration": "25"}},
            }
        )

        result = parser.parse(content, "Starte timer")
        self.assertEqual("Alles klar", result["assistant_text"])
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call to be present")
        self.assertEqual("start_timer", tool_call["name"])
        self.assertEqual("25", tool_call["arguments"]["duration"])

    def test_non_json_fallback_infers_start_timer(self) -> None:
        parser = ResponseParser()
        result = parser.parse("not json", "Starte einen Timer fuer 15 Minuten")

        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected inferred tool_call")
        self.assertEqual("start_timer", tool_call["name"])
        self.assertEqual("15m", tool_call["arguments"]["duration"])

    def test_legacy_timer_start_with_focus_maps_to_pomodoro(self) -> None:
        parser = ResponseParser()
        content = json.dumps(
            {
                "assistant_text": "",
                "tool_call": {
                    "name": "timer_start",
                    "arguments": {"focus_topic": "Code Review"},
                },
            }
        )
        result = parser.parse(content, "Starte")

        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected normalized tool_call")
        self.assertEqual("start_pomodoro_session", tool_call["name"])
        self.assertEqual("Code Review", tool_call["arguments"]["focus_topic"])

    def test_legacy_timer_start_ambiguous_defaults_to_pomodoro(self) -> None:
        parser = ResponseParser()
        content = json.dumps(
            {
                "assistant_text": "",
                "tool_call": {
                    "name": "timer_start",
                    "arguments": {},
                },
            }
        )
        result = parser.parse(content, "Bitte starte")

        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected normalized tool_call")
        self.assertEqual("start_pomodoro_session", tool_call["name"])
        self.assertEqual("Fokus", tool_call["arguments"]["focus_topic"])

    def test_english_assistant_text_replaced_with_german_fallback(self) -> None:
        parser = ResponseParser()
        content = json.dumps(
            {
                "assistant_text": "Sure, starting it now.",
                "tool_call": {
                    "name": "start_timer",
                    "arguments": {"duration": "10"},
                },
            }
        )
        result = parser.parse(content, "Starte timer")
        self.assertEqual("Ich starte den Timer mit der Dauer 10.", result["assistant_text"])

    def test_add_calendar_event_missing_start_time_rejected(self) -> None:
        parser = ResponseParser()
        content = json.dumps(
            {
                "assistant_text": "",
                "tool_call": {
                    "name": "add_calendar_event",
                    "arguments": {"title": "Demo"},
                },
            }
        )
        result = parser.parse(content, "Bitte fuege Kalender Event 'Demo' hinzu")

        self.assertIsNone(result["tool_call"])

    def test_show_events_infers_time_range_morgen(self) -> None:
        parser = ResponseParser()
        result = parser.parse("", "Zeige mir kommende Termine morgen")

        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected inferred tool_call")
        self.assertEqual("show_upcoming_events", tool_call["name"])
        self.assertEqual("morgen", tool_call["arguments"]["time_range"])

    def test_relative_datetime_extraction_is_deterministic(self) -> None:
        parser = ResponseParser()
        content = json.dumps(
            {
                "assistant_text": "",
                "tool_call": {
                    "name": "add_calendar_event",
                    "arguments": {"title": "Review"},
                },
            }
        )

        with patch("llm.parser.datetime", _FrozenDateTime):
            result = parser.parse(
                content,
                "Bitte fuege den Kalender Termin hinzu morgen um 9 uhr",
            )

        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected normalized calendar tool_call")
        self.assertEqual("add_calendar_event", tool_call["name"])
        expected = (
            _FrozenDateTime.now().astimezone() + timedelta(days=1)
        ).replace(
            hour=9,
            minute=0,
            second=0,
            microsecond=0,
        )
        self.assertEqual(
            expected.isoformat(timespec="minutes"),
            tool_call["arguments"]["start_time"],
        )


if __name__ == "__main__":
    unittest.main()

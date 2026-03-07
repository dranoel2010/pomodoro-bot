from __future__ import annotations

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

    def test_fast_path_routes_status_query_to_status_pomodoro(self) -> None:
        result = maybe_fast_path_response("Wie lange laeuft die Pomodoro Sitzung noch?")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("status_pomodoro_session", tool_call["name"])

    def test_fast_path_routes_status_keyword_with_pomodoro_context(self) -> None:
        result = maybe_fast_path_response("Status der Pomodoro Sitzung")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("status_pomodoro_session", tool_call["name"])

    def test_fast_path_stop_pomodoro_not_misrouted_as_status(self) -> None:
        # "stopp" (imperative without trailing 'e') matches detect_action INTENT_STOP
        result = maybe_fast_path_response("Stopp die Pomodoro Sitzung")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("stop_pomodoro_session", tool_call["name"])

    def test_fast_path_noch_mal_not_misrouted_as_status(self) -> None:
        # "noch" removed from status pattern; "noch mal" should fall through to LLM
        result = maybe_fast_path_response("Starte die Pomodoro Sitzung noch mal")
        # fast-path detects "start" action + pomodoro context → start_pomodoro_session (not status)
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("start_pomodoro_session", tool_call["name"])

    def test_fast_path_uses_parser_rules_not_response_parser(self) -> None:
        with patch("llm.fast_path.fallback_assistant_text", return_value="Timer gestoppt."):
            result = maybe_fast_path_response("Stopp den Timer")

        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response")
        self.assertEqual("Timer gestoppt.", result["assistant_text"])
        self.assertEqual("stop_timer", result["tool_call"]["name"])

    def test_fast_path_routes_show_events_to_show_upcoming_events(self) -> None:
        # "Zeige mir meine Termine heute" satisfies both has_calendar ("termine")
        # and has_show ("zeige") predicates in looks_like_show_events().
        # No oracle is involved — routing is purely deterministic (AC #1, #4).
        result = maybe_fast_path_response("Zeige mir meine Termine heute")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response for calendar show query")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("show_upcoming_events", tool_call["name"])
        self.assertIn("time_range", tool_call["arguments"])
        self.assertEqual("heute", tool_call["arguments"]["time_range"])

    def test_fast_path_show_events_does_not_require_oracle(self) -> None:
        # maybe_fast_path_response takes only the prompt — no oracle parameter.
        # A successful routing result proves oracle is not required (AC #1, #4).
        result = maybe_fast_path_response("Welche Termine habe ich naechste Woche?")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("show_upcoming_events", tool_call["name"])
        self.assertEqual("naechste woche", tool_call["arguments"].get("time_range"))

    def test_fast_path_routes_add_event_when_title_and_time_present(self) -> None:
        # looks_like_add_calendar() requires BOTH a calendar keyword ("termin")
        # and a creation verb ("anlegen"). extract_calendar_title() extracts the
        # quoted title; extract_datetime_literal() extracts the relative datetime.
        # If either title or start_time is missing the fast-path returns None.
        result = maybe_fast_path_response('Termin "Meeting" anlegen morgen um 10 Uhr')
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path response for add-event query")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("add_calendar_event", tool_call["name"])
        self.assertIn("title", tool_call["arguments"])
        self.assertIn("start_time", tool_call["arguments"])
        self.assertEqual("Meeting", tool_call["arguments"]["title"])

    def test_fast_path_add_event_missing_datetime_returns_none(self) -> None:
        # looks_like_add_calendar() fires but extract_datetime_literal() returns None
        # → fast-path falls through to LLM rather than emitting a broken tool call.
        result = maybe_fast_path_response('Termin "Standup" anlegen')
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

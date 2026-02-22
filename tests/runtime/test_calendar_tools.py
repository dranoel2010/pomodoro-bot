import datetime as dt
import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Import runtime.calendar_tools without executing src/runtime/__init__.py.
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg

from runtime.calendar_tools import (
    format_calendar_value_natural,
    format_calendar_window_natural,
    handle_calendar_tool_call,
    parse_calendar_datetime,
    parse_duration_seconds,
)


class _FrozenDateTime(dt.datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        base = dt.datetime(2026, 2, 21, 10, 0, tzinfo=dt.timezone.utc)
        if tz is not None:
            return base.astimezone(tz)
        return base


class _OracleStub:
    def __init__(self, *, events=None, event_id: str = "evt-1"):
        self._events = list(events or [])
        self._event_id = event_id
        self.list_calls: list[dict[str, object]] = []
        self.add_calls: list[dict[str, object]] = []

    def list_upcoming_events(self, *, max_results: int, time_min: dt.datetime):
        self.list_calls.append({"max_results": max_results, "time_min": time_min})
        return list(self._events)

    def add_event(self, *, title: str, start: dt.datetime, end: dt.datetime) -> str:
        self.add_calls.append({"title": title, "start": start, "end": end})
        return self._event_id


class _OracleSettingsStub:
    def __init__(self, *, max_results: int = 3):
        self.google_calendar_max_results = max_results


class _AppConfigStub:
    def __init__(self, *, max_results: int = 3):
        self.oracle = _OracleSettingsStub(max_results=max_results)


class CalendarToolsTests(unittest.TestCase):
    def test_window_format_uses_spoken_time(self) -> None:
        now = dt.datetime(2026, 2, 21, 10, 0, tzinfo=dt.timezone.utc)
        start = dt.datetime(2026, 2, 21, 8, 0, tzinfo=dt.timezone.utc)
        end = dt.datetime(2026, 2, 21, 14, 45, tzinfo=dt.timezone.utc)
        text = format_calendar_window_natural(start, end, now=now)
        self.assertEqual("heute von 8 Uhr bis 14 Uhr 45", text)

    def test_parse_duration_seconds_supports_common_units(self) -> None:
        self.assertEqual(15 * 60, parse_duration_seconds("15", default_seconds=60))
        self.assertEqual(90, parse_duration_seconds("90s", default_seconds=60))
        self.assertEqual(2 * 3600, parse_duration_seconds("2h", default_seconds=60))
        self.assertEqual(7 * 60, parse_duration_seconds(7, default_seconds=60))

    def test_parse_calendar_datetime_accepts_german_format(self) -> None:
        parsed = parse_calendar_datetime("22.02.2026 09:15")
        self.assertIsNotNone(parsed)
        if parsed is None:
            self.fail("Expected parsed datetime")
        self.assertEqual(2026, parsed.year)
        self.assertEqual(2, parsed.month)
        self.assertEqual(22, parsed.day)
        self.assertEqual(9, parsed.hour)
        self.assertEqual(15, parsed.minute)
        self.assertIsNotNone(parsed.tzinfo)

    def test_parse_calendar_datetime_accepts_relative_german_format(self) -> None:
        with patch("runtime.calendar_tools.dt.datetime", _FrozenDateTime):
            parsed = parse_calendar_datetime("heute 10 Uhr")

        self.assertIsNotNone(parsed)
        if parsed is None:
            self.fail("Expected parsed datetime")
        expected = _FrozenDateTime.now().astimezone().replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0,
        )
        self.assertEqual(expected, parsed)

    def test_parse_calendar_datetime_accepts_relative_dot_time(self) -> None:
        with patch("runtime.calendar_tools.dt.datetime", _FrozenDateTime):
            parsed = parse_calendar_datetime("heute 0.45 Uhr")

        self.assertIsNotNone(parsed)
        if parsed is None:
            self.fail("Expected parsed datetime")
        expected = _FrozenDateTime.now().astimezone().replace(
            hour=0,
            minute=45,
            second=0,
            microsecond=0,
        )
        self.assertEqual(expected, parsed)

    def test_show_upcoming_events_filters_by_time_range(self) -> None:
        oracle = _OracleStub(
            events=[
                {"summary": "Standup", "start": "2026-02-22T09:00:00+00:00"},
                {"summary": "Far Future", "start": "2026-03-01T09:00:00+00:00"},
            ]
        )
        app_config = _AppConfigStub(max_results=3)

        with patch("runtime.calendar_tools.dt.datetime", _FrozenDateTime):
            message = handle_calendar_tool_call(
                tool_name="show_upcoming_events",
                arguments={"time_range": "morgen"},
                oracle_service=oracle,
                app_config=app_config,
                logger=logging.getLogger("test"),
            )
            expected_start_text = format_calendar_value_natural(
                "2026-02-22T09:00:00+00:00",
                now=_FrozenDateTime.now().astimezone(),
            )

        self.assertIn("Standup", message)
        self.assertNotIn("Far Future", message)
        self.assertIsNotNone(expected_start_text)
        if expected_start_text is not None:
            self.assertIn(expected_start_text, message)
        self.assertEqual(1, len(oracle.list_calls))
        self.assertEqual(6, oracle.list_calls[0]["max_results"])

    def test_add_calendar_event_uses_duration_when_end_missing(self) -> None:
        oracle = _OracleStub(event_id="evt-42")
        app_config = _AppConfigStub()

        with patch("runtime.calendar_tools.dt.datetime", _FrozenDateTime):
            message = handle_calendar_tool_call(
                tool_name="add_calendar_event",
                arguments={
                    "title": "Review",
                    "start_time": "2026-02-21T12:00:00+00:00",
                    "duration": "45",
                },
                oracle_service=oracle,
                app_config=app_config,
                logger=logging.getLogger("test"),
            )

        self.assertIn("Termin angelegt: Review", message)
        self.assertEqual(1, len(oracle.add_calls))
        start = oracle.add_calls[0]["start"]
        end = oracle.add_calls[0]["end"]
        self.assertIsInstance(start, dt.datetime)
        self.assertIsInstance(end, dt.datetime)
        if not isinstance(start, dt.datetime) or not isinstance(end, dt.datetime):
            self.fail("Expected datetime arguments")
        self.assertEqual(45 * 60, int((end - start).total_seconds()))
        expected_window = format_calendar_window_natural(
            start,
            end,
            now=_FrozenDateTime.now().astimezone(),
        )
        self.assertIn(f"Zeit: {expected_window}", message)

    def test_add_calendar_event_accepts_relative_start_time(self) -> None:
        oracle = _OracleStub(event_id="evt-77")
        app_config = _AppConfigStub()

        with patch("runtime.calendar_tools.dt.datetime", _FrozenDateTime):
            message = handle_calendar_tool_call(
                tool_name="add_calendar_event",
                arguments={
                    "title": "Leo treffen",
                    "start_time": "heute 10 Uhr",
                },
                oracle_service=oracle,
                app_config=app_config,
                logger=logging.getLogger("test"),
            )

        self.assertIn("Termin angelegt: Leo treffen", message)
        self.assertEqual(1, len(oracle.add_calls))
        start = oracle.add_calls[0]["start"]
        end = oracle.add_calls[0]["end"]
        self.assertIsInstance(start, dt.datetime)
        self.assertIsInstance(end, dt.datetime)
        if not isinstance(start, dt.datetime) or not isinstance(end, dt.datetime):
            self.fail("Expected datetime arguments")
        self.assertEqual(30 * 60, int((end - start).total_seconds()))
        expected_window = format_calendar_window_natural(
            start,
            end,
            now=_FrozenDateTime.now().astimezone(),
        )
        self.assertIn(f"Zeit: {expected_window}", message)

    def test_calendar_tools_require_oracle_service(self) -> None:
        message = handle_calendar_tool_call(
            tool_name="show_upcoming_events",
            arguments={"time_range": "heute"},
            oracle_service=None,
            app_config=_AppConfigStub(),
            logger=logging.getLogger("test"),
        )
        self.assertEqual("Kalenderfunktion ist derzeit nicht verfuegbar.", message)


if __name__ == "__main__":
    unittest.main()

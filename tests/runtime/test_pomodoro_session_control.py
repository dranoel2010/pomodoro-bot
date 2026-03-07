from __future__ import annotations

import logging
import sys
import types
import unittest
from pathlib import Path

from pomodoro import PomodoroTimer

# Import runtime modules without executing src/runtime/__init__.py.
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg

from runtime.tools.dispatch import RuntimeToolDispatcher
from runtime.ui import RuntimeUIPublisher


class _UIServerStub:
    def __init__(self):
        self.events: list[tuple[str, dict[str, object]]] = []
        self.states: list[tuple[str, str | None, dict[str, object]]] = []

    def publish(self, event_type: str, **payload):
        self.events.append((event_type, payload))

    def publish_state(self, state: str, *, message=None, **payload):
        self.states.append((state, message, payload))


class _OracleSettingsStub:
    google_calendar_max_results = 3


class _AppConfigStub:
    oracle = _OracleSettingsStub()


class PomodoroSessionControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ui_server = _UIServerStub()
        self.ui = RuntimeUIPublisher(self.ui_server)
        self.pomodoro_timer = PomodoroTimer(duration_seconds=25 * 60)
        self.timer = PomodoroTimer(duration_seconds=10 * 60)
        self.dispatcher = RuntimeToolDispatcher(
            logger=logging.getLogger("test"),
            app_config=_AppConfigStub(),
            oracle_service=None,
            pomodoro_timer=self.pomodoro_timer,
            countdown_timer=self.timer,
            ui=self.ui,
        )

    # AC #1 — start when idle → running, German confirmation, start time recorded
    def test_start_when_idle_transitions_to_running(self) -> None:
        response = self.dispatcher.handle_tool_call(
            {"name": "start_pomodoro_session", "arguments": {"focus_topic": "Fokus"}},
            "",
        )

        snapshot = self.pomodoro_timer.snapshot()
        self.assertEqual("running", snapshot.phase)
        self.assertGreater(snapshot.remaining_seconds, 0)  # AC #1: start time recorded
        self.assertIn("starte", response.lower())

    # AC #2 — stop when running → aborted, German confirmation
    def test_stop_when_running_transitions_to_aborted(self) -> None:
        self.pomodoro_timer.apply("start", session="Fokus")

        response = self.dispatcher.handle_tool_call(
            {"name": "stop_pomodoro_session", "arguments": {}},
            "",
        )

        self.assertEqual("aborted", self.pomodoro_timer.snapshot().phase)
        self.assertIn("stoppe", response.lower())

    # AC #3 — status when running → German remaining time text
    def test_status_when_running_returns_remaining_time(self) -> None:
        self.pomodoro_timer.apply("start", session="Fokus")

        response = self.dispatcher.handle_tool_call(
            {"name": "status_pomodoro_session", "arguments": {}},
            "",
        )

        self.assertIn("laeuft", response)
        self.assertIn("verbleibend", response)
        # No UI events published for read-only status query
        self.assertFalse(any(kind == "pomodoro" for kind, _ in self.ui_server.events))

    # AC #4 — stop when idle → rejection text
    def test_stop_when_idle_returns_rejection_text(self) -> None:
        response = self.dispatcher.handle_tool_call(
            {"name": "stop_pomodoro_session", "arguments": {}},
            "",
        )

        self.assertEqual("idle", self.pomodoro_timer.snapshot().phase)
        self.assertIn("keine aktive", response.lower())

    # AC #4 — status when idle → idle message
    def test_status_when_idle_returns_no_active_session_message(self) -> None:
        response = self.dispatcher.handle_tool_call(
            {"name": "status_pomodoro_session", "arguments": {}},
            "",
        )

        self.assertEqual("Keine aktive Pomodoro-Sitzung.", response)
        # No UI events published for read-only status query
        self.assertFalse(any(kind == "pomodoro" for kind, _ in self.ui_server.events))

    # abort then start again → fresh running state (session reset)
    def test_abort_then_restart_begins_fresh_session(self) -> None:
        self.dispatcher.handle_tool_call(
            {"name": "start_pomodoro_session", "arguments": {"focus_topic": "Fokus"}},
            "",
        )
        stop_response = self.dispatcher.handle_tool_call(
            {"name": "stop_pomodoro_session", "arguments": {}},
            "",
        )
        self.assertEqual("aborted", self.pomodoro_timer.snapshot().phase)
        self.assertIn("stoppe", stop_response.lower())

        restart_response = self.dispatcher.handle_tool_call(
            {"name": "start_pomodoro_session", "arguments": {"focus_topic": "Fokus"}},
            "",
        )

        self.assertEqual("running", self.pomodoro_timer.snapshot().phase)
        self.assertIn("starte", restart_response.lower())


if __name__ == "__main__":
    unittest.main()

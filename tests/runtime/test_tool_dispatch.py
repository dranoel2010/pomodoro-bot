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

from runtime.tool_dispatch import RuntimeToolDispatcher
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


class RuntimeToolDispatcherTests(unittest.TestCase):
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

    def _last_event(self, event_type: str) -> dict[str, object]:
        for kind, payload in reversed(self.ui_server.events):
            if kind == event_type:
                return payload
        self.fail(f"Expected {event_type} event")

    def test_pause_timer_maps_to_pause_pomodoro_when_pomodoro_active(self) -> None:
        self.pomodoro_timer.apply("start", session="Deep Work")

        response = self.dispatcher.handle_tool_call(
            {"name": "pause_timer", "arguments": {}},
            "",
        )

        self.assertIn("Pomodoro", response)
        self.assertEqual("paused", self.pomodoro_timer.snapshot().phase)
        self.assertEqual("idle", self.timer.snapshot().phase)
        pomodoro_event = self._last_event("pomodoro")
        self.assertEqual("pause_pomodoro_session", pomodoro_event.get("tool_name"))
        self.assertTrue(bool(pomodoro_event.get("accepted")))

    def test_start_timer_maps_to_start_pomodoro_when_pomodoro_active(self) -> None:
        self.pomodoro_timer.apply("start", session="Focus")

        self.dispatcher.handle_tool_call(
            {"name": "start_timer", "arguments": {"duration": "5"}},
            "",
        )

        self.assertEqual("running", self.pomodoro_timer.snapshot().phase)
        self.assertEqual("idle", self.timer.snapshot().phase)
        pomodoro_event = self._last_event("pomodoro")
        self.assertEqual("start_pomodoro_session", pomodoro_event.get("tool_name"))
        self.assertTrue(bool(pomodoro_event.get("accepted")))
        self.assertFalse(any(kind == "timer" for kind, _ in self.ui_server.events))

    def test_start_pomodoro_stops_running_timer_first(self) -> None:
        self.timer.apply("start", session="Timer", duration_seconds=10 * 60)

        self.dispatcher.handle_tool_call(
            {
                "name": "start_pomodoro_session",
                "arguments": {"focus_topic": "Write tests"},
            },
            "",
        )

        self.assertEqual("aborted", self.timer.snapshot().phase)
        self.assertEqual("running", self.pomodoro_timer.snapshot().phase)
        timer_events = [payload for kind, payload in self.ui_server.events if kind == "timer"]
        self.assertTrue(timer_events)
        self.assertIn(
            True,
            [
                event.get("reason") == "superseded_by_pomodoro"
                and event.get("action") == "abort"
                for event in timer_events
            ],
        )

    def test_pause_pomodoro_rejected_while_timer_active(self) -> None:
        self.timer.apply("start", session="Timer", duration_seconds=10 * 60)

        response = self.dispatcher.handle_tool_call(
            {"name": "pause_pomodoro_session", "arguments": {}},
            "",
        )

        self.assertEqual(
            "Es laeuft bereits ein Timer. Bitte stoppe den Timer zuerst.",
            response,
        )
        self.assertEqual("running", self.timer.snapshot().phase)
        self.assertEqual("idle", self.pomodoro_timer.snapshot().phase)
        pomodoro_event = self._last_event("pomodoro")
        self.assertFalse(bool(pomodoro_event.get("accepted")))
        self.assertEqual("timer_active", pomodoro_event.get("reason"))


if __name__ == "__main__":
    unittest.main()

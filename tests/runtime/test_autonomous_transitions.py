from __future__ import annotations

import logging
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from pomodoro import PomodoroCycleState, PomodoroTimer
from pomodoro.constants import (
    DEFAULT_POMODORO_SECONDS,
    DEFAULT_SHORT_BREAK_SECONDS,
    PHASE_TYPE_SHORT_BREAK,
    PHASE_TYPE_WORK,
)

# Import runtime submodules without executing src/runtime/__init__.py.
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg


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


with patch.dict(sys.modules, _build_tts_stub_modules()):
    from runtime.ticks import handle_pomodoro_tick

from runtime.tools.dispatch import RuntimeToolDispatcher
from runtime.ui import RuntimeUIPublisher
from contracts.ui_protocol import EVENT_ASSISTANT_REPLY, STATE_REPLYING


class _UIServerStub:
    def __init__(self):
        self.events: list[tuple[str, dict[str, object]]] = []
        self.states: list[tuple[str, str | None, dict[str, object]]] = []
        self.pomodoro_events: list[dict[str, object]] = []
        self.timer_events: list[dict[str, object]] = []
        self.trace: list[tuple[str, str]] = []

    def publish(self, event_type: str, **payload):
        self.events.append((event_type, payload))
        self.trace.append(("event", event_type))

    def publish_state(self, state: str, *, message=None, **payload):
        self.states.append((state, message, payload))
        self.trace.append(("state", state))

    def publish_pomodoro_update(self, snapshot, **payload):
        self.pomodoro_events.append(payload)
        self.trace.append(("event", "pomodoro"))

    def publish_timer_update(self, snapshot, **payload):
        self.timer_events.append(payload)
        self.trace.append(("event", "timer"))


class _OracleSettingsStub:
    google_calendar_max_results = 3


class _AppConfigStub:
    oracle = _OracleSettingsStub()


def _make_completed_tick(timer: PomodoroTimer):
    """Fast-forward the timer to completion and return the completed tick."""
    future_time = time.monotonic() + 100_000.0
    with patch("time.monotonic", return_value=future_time):
        tick = timer.poll()
    return tick


class AutonomousTransitionTests(unittest.TestCase):
    def _make_ui(self):
        stub = _UIServerStub()
        return RuntimeUIPublisher(stub), stub

    def test_work_to_break_transition_fires_on_tick_completion(self) -> None:
        ui, stub = self._make_ui()
        idle_calls: list[str] = []
        cycle = PomodoroCycleState()
        cycle.begin_cycle(session_name="Fokus")

        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")
        tick = _make_completed_tick(timer)

        self.assertIsNotNone(tick)
        self.assertTrue(tick.completed)

        handle_pomodoro_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: idle_calls.append("idle"),
            pomodoro_timer=timer,
            cycle=cycle,
        )

        # Cycle advanced to short_break
        self.assertEqual(PHASE_TYPE_SHORT_BREAK, cycle.phase_type)
        self.assertEqual(1, cycle.session_count)

        # Timer reset to break duration and running
        snapshot = timer.snapshot()
        self.assertEqual("running", snapshot.phase)
        self.assertEqual("Kurze Pause", snapshot.session)
        self.assertEqual(DEFAULT_SHORT_BREAK_SECONDS, snapshot.duration_seconds)

        # Idle state published after announcement — timer is already running for the
        # new phase, so active_runtime_message() shows the break status, not idle.
        self.assertEqual(["idle"], idle_calls)

        # UI events published
        replying_states = [s for s, _, _ in stub.states if s == STATE_REPLYING]
        self.assertEqual(1, len(replying_states))
        assistant_events = [p for kind, p in stub.events if kind == EVENT_ASSISTANT_REPLY]
        self.assertEqual(1, len(assistant_events))

    def test_break_to_work_transition_fires_on_break_completion(self) -> None:
        ui, stub = self._make_ui()
        idle_calls: list[str] = []
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")

        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")

        # First: advance work phase
        work_tick = _make_completed_tick(timer)
        self.assertIsNotNone(work_tick)
        handle_pomodoro_tick(
            work_tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: idle_calls.append("idle"),
            pomodoro_timer=timer,
            cycle=cycle,
        )
        self.assertEqual(PHASE_TYPE_SHORT_BREAK, cycle.phase_type)
        self.assertEqual(1, cycle.session_count)

        # Now advance break phase
        stub.events.clear()
        stub.states.clear()
        break_tick = _make_completed_tick(timer)
        self.assertIsNotNone(break_tick)
        handle_pomodoro_tick(
            break_tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: idle_calls.append("idle"),
            pomodoro_timer=timer,
            cycle=cycle,
        )

        self.assertEqual(PHASE_TYPE_WORK, cycle.phase_type)
        self.assertEqual(1, cycle.session_count)  # unchanged by break→work

        snapshot = timer.snapshot()
        self.assertEqual("running", snapshot.phase)
        self.assertEqual("Fokus", snapshot.session)
        self.assertEqual(2, snapshot.duration_seconds)

        # Both transitions publish idle state (once per announcement)
        self.assertEqual(["idle", "idle"], idle_calls)

        assistant_events = [p for kind, p in stub.events if kind == EVENT_ASSISTANT_REPLY]
        self.assertEqual(1, len(assistant_events))

    def test_session_count_increments_only_on_work_completion(self) -> None:
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        ui, _ = self._make_ui()
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")

        for _ in range(2):
            # Work → break
            work_tick = _make_completed_tick(timer)
            handle_pomodoro_tick(
                work_tick,
                speech_service=None,
                logger=logging.getLogger("test"),
                ui=ui,
                publish_idle_state=lambda: None,
                pomodoro_timer=timer,
                cycle=cycle,
            )
            # Break → work
            break_tick = _make_completed_tick(timer)
            handle_pomodoro_tick(
                break_tick,
                speech_service=None,
                logger=logging.getLogger("test"),
                ui=ui,
                publish_idle_state=lambda: None,
                pomodoro_timer=timer,
                cycle=cycle,
            )

        self.assertEqual(2, cycle.session_count)

    def test_cycle_inactive_preserves_existing_idle_behavior(self) -> None:
        from pomodoro import PomodoroSnapshot, PomodoroTick

        ui, _ = self._make_ui()
        idle_calls: list[str] = []
        cycle = PomodoroCycleState()
        # cycle.begin_cycle() NOT called — cycle is inactive

        tick = PomodoroTick(
            snapshot=PomodoroSnapshot(
                phase="completed",
                session="Fokus",
                duration_seconds=25 * 60,
                remaining_seconds=0,
            ),
            completed=True,
        )
        timer = PomodoroTimer(duration_seconds=25 * 60)

        handle_pomodoro_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: idle_calls.append("idle"),
            pomodoro_timer=timer,
            cycle=cycle,
        )

        self.assertEqual(["idle"], idle_calls)

    def test_cycle_none_preserves_existing_idle_behavior(self) -> None:
        from pomodoro import PomodoroSnapshot, PomodoroTick

        ui, _ = self._make_ui()
        idle_calls: list[str] = []
        tick = PomodoroTick(
            snapshot=PomodoroSnapshot(
                phase="completed",
                session="Fokus",
                duration_seconds=25 * 60,
                remaining_seconds=0,
            ),
            completed=True,
        )

        handle_pomodoro_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: idle_calls.append("idle"),
            cycle=None,
        )

        self.assertEqual(["idle"], idle_calls)

    def test_dispatcher_begin_cycle_called_on_start(self) -> None:
        ui_server = _UIServerStub()
        ui = RuntimeUIPublisher(ui_server)
        pomodoro_timer = PomodoroTimer(duration_seconds=25 * 60)
        countdown_timer = PomodoroTimer(duration_seconds=10 * 60)
        cycle = PomodoroCycleState()

        dispatcher = RuntimeToolDispatcher(
            logger=logging.getLogger("test"),
            app_config=_AppConfigStub(),
            oracle_service=None,
            pomodoro_timer=pomodoro_timer,
            countdown_timer=countdown_timer,
            ui=ui,
            pomodoro_cycle=cycle,
        )

        dispatcher.handle_tool_call(
            {"name": "start_pomodoro_session", "arguments": {"focus_topic": "Fokus"}},
            "",
        )

        self.assertTrue(cycle.active)
        self.assertEqual(PHASE_TYPE_WORK, cycle.phase_type)
        self.assertEqual(0, cycle.session_count)

    def test_dispatcher_reset_called_on_stop(self) -> None:
        ui_server = _UIServerStub()
        ui = RuntimeUIPublisher(ui_server)
        pomodoro_timer = PomodoroTimer(duration_seconds=25 * 60)
        countdown_timer = PomodoroTimer(duration_seconds=10 * 60)
        cycle = PomodoroCycleState()

        dispatcher = RuntimeToolDispatcher(
            logger=logging.getLogger("test"),
            app_config=_AppConfigStub(),
            oracle_service=None,
            pomodoro_timer=pomodoro_timer,
            countdown_timer=countdown_timer,
            ui=ui,
            pomodoro_cycle=cycle,
        )

        # Start first so we can then stop
        dispatcher.handle_tool_call(
            {"name": "start_pomodoro_session", "arguments": {"focus_topic": "Fokus"}},
            "",
        )
        self.assertTrue(cycle.active)

        dispatcher.handle_tool_call(
            {"name": "stop_pomodoro_session", "arguments": {}},
            "",
        )

        self.assertFalse(cycle.active)

    def test_dispatcher_begin_cycle_called_on_reset(self) -> None:
        ui_server = _UIServerStub()
        ui = RuntimeUIPublisher(ui_server)
        pomodoro_timer = PomodoroTimer(duration_seconds=25 * 60)
        countdown_timer = PomodoroTimer(duration_seconds=10 * 60)
        cycle = PomodoroCycleState()

        dispatcher = RuntimeToolDispatcher(
            logger=logging.getLogger("test"),
            app_config=_AppConfigStub(),
            oracle_service=None,
            pomodoro_timer=pomodoro_timer,
            countdown_timer=countdown_timer,
            ui=ui,
            pomodoro_cycle=cycle,
        )

        # Start, then reset with a new session name
        dispatcher.handle_tool_call(
            {"name": "start_pomodoro_session", "arguments": {"focus_topic": "Fokus"}},
            "",
        )
        self.assertTrue(cycle.active)
        self.assertEqual(0, cycle.session_count)

        dispatcher.handle_tool_call(
            {"name": "reset_pomodoro_session", "arguments": {"focus_topic": "Neue Session"}},
            "",
        )

        # Reset re-invokes begin_cycle: active again, count zeroed, phase back to work
        self.assertTrue(cycle.active)
        self.assertEqual(PHASE_TYPE_WORK, cycle.phase_type)
        self.assertEqual(0, cycle.session_count)


if __name__ == "__main__":
    unittest.main()

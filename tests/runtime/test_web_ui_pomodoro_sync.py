"""Tests for WebSocket UI synchronisation of Pomodoro cycle state (Story 3-4)."""

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
    PHASE_TYPE_LONG_BREAK,
    PHASE_TYPE_SHORT_BREAK,
    PHASE_TYPE_WORK,
    SESSIONS_PER_CYCLE,
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

    class TTSError(Exception):
        pass

    engine_module.TTSError = TTSError
    return {
        "tts": package,
        "tts.engine": engine_module,
    }


with patch.dict(sys.modules, _build_tts_stub_modules()):
    from runtime.ticks import handle_pomodoro_tick

from runtime.tools.dispatch import RuntimeToolDispatcher
from runtime.ui import RuntimeUIPublisher
from contracts.ui_protocol import (
    EVENT_POMODORO,
    STATE_POMODORO_IDLE,
    STATE_POMODORO_LONG_BREAK,
    STATE_POMODORO_SHORT_BREAK,
    STATE_POMODORO_WORK,
)


class _UIServerStub:
    def __init__(self):
        self.events: list[tuple[str, dict[str, object]]] = []
        self.states: list[tuple[str, str | None]] = []

    def publish(self, event_type: str, **payload):
        self.events.append((event_type, payload))

    def publish_state(self, state: str, *, message=None, **payload):
        self.states.append((state, message))

    def pomodoro_payloads(self) -> list[dict[str, object]]:
        return [p for kind, p in self.events if kind == EVENT_POMODORO]


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


class DispatchCycleSyncTests(unittest.TestCase):
    """Tests for dispatch-triggered cycle phase broadcasts (start, stop, reset)."""

    def _make_dispatcher(self):
        stub = _UIServerStub()
        ui = RuntimeUIPublisher(stub)
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
        return dispatcher, stub, cycle

    def test_start_broadcasts_pomodoro_work_phase(self):
        dispatcher, stub, _ = self._make_dispatcher()
        dispatcher.handle_tool_call({"name": "start_pomodoro_session", "arguments": {}}, "")
        payloads = stub.pomodoro_payloads()
        self.assertTrue(payloads)
        last = payloads[-1]
        self.assertEqual(STATE_POMODORO_WORK, last.get("cycle_phase"))
        self.assertEqual(0, last.get("session_count"))

    def test_stop_broadcasts_pomodoro_idle_phase(self):
        dispatcher, stub, _ = self._make_dispatcher()
        dispatcher.handle_tool_call({"name": "start_pomodoro_session", "arguments": {}}, "")
        stub.events.clear()
        dispatcher.handle_tool_call({"name": "stop_pomodoro_session", "arguments": {}}, "")
        payloads = stub.pomodoro_payloads()
        self.assertTrue(payloads)
        last = payloads[-1]
        self.assertEqual(STATE_POMODORO_IDLE, last.get("cycle_phase"))
        self.assertEqual(0, last.get("session_count"))

    def test_reset_broadcasts_pomodoro_work_phase(self):
        dispatcher, stub, _ = self._make_dispatcher()
        dispatcher.handle_tool_call({"name": "start_pomodoro_session", "arguments": {}}, "")
        stub.events.clear()
        dispatcher.handle_tool_call({"name": "reset_pomodoro_session", "arguments": {}}, "")
        payloads = stub.pomodoro_payloads()
        self.assertTrue(payloads)
        last = payloads[-1]
        self.assertEqual(STATE_POMODORO_WORK, last.get("cycle_phase"))
        self.assertEqual(0, last.get("session_count"))


class TicksCycleSyncTests(unittest.TestCase):
    """Tests for autonomous transition broadcasts and tick event broadcasts."""

    def _make_ui(self):
        stub = _UIServerStub()
        return RuntimeUIPublisher(stub), stub

    def _advance_tick(
        self,
        timer: PomodoroTimer,
        cycle: PomodoroCycleState,
        ui: RuntimeUIPublisher,
    ) -> None:
        """Drive a single autonomous transition via handle_pomodoro_tick."""
        tick = _make_completed_tick(timer)
        handle_pomodoro_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: None,
            pomodoro_timer=timer,
            cycle=cycle,
        )

    def test_work_to_short_break_broadcasts_short_break_phase(self):
        ui, stub = self._make_ui()
        cycle = PomodoroCycleState()
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")
        tick = _make_completed_tick(timer)
        handle_pomodoro_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: None,
            pomodoro_timer=timer,
            cycle=cycle,
        )
        payloads = stub.pomodoro_payloads()
        completed_payloads = [p for p in payloads if p.get("action") == "completed"]
        self.assertEqual(1, len(completed_payloads))
        self.assertEqual(STATE_POMODORO_SHORT_BREAK, completed_payloads[0].get("cycle_phase"))
        self.assertEqual(1, completed_payloads[0].get("session_count"))

    def test_short_break_to_work_broadcasts_work_phase(self):
        ui, stub = self._make_ui()
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")
        # Work → short break
        self._advance_tick(timer, cycle, ui)
        self.assertEqual(PHASE_TYPE_SHORT_BREAK, cycle.phase_type)
        stub.events.clear()
        # Short break → work
        self._advance_tick(timer, cycle, ui)
        payloads = stub.pomodoro_payloads()
        completed_payloads = [p for p in payloads if p.get("action") == "completed"]
        self.assertEqual(1, len(completed_payloads))
        self.assertEqual(STATE_POMODORO_WORK, completed_payloads[0].get("cycle_phase"))
        self.assertEqual(1, completed_payloads[0].get("session_count"))

    def test_work_to_long_break_broadcasts_long_break_phase(self):
        ui, stub = self._make_ui()
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")
        # Advance through sessions 1–(SESSIONS_PER_CYCLE-1): work→short_break→work
        for _ in range(SESSIONS_PER_CYCLE - 1):
            self._advance_tick(timer, cycle, ui)  # work → short_break
            self.assertEqual(PHASE_TYPE_SHORT_BREAK, cycle.phase_type)
            self._advance_tick(timer, cycle, ui)  # short_break → work
            self.assertEqual(PHASE_TYPE_WORK, cycle.phase_type)
        stub.events.clear()
        # Final work session → long break
        self._advance_tick(timer, cycle, ui)
        payloads = stub.pomodoro_payloads()
        completed_payloads = [p for p in payloads if p.get("action") == "completed"]
        self.assertEqual(1, len(completed_payloads))
        self.assertEqual(STATE_POMODORO_LONG_BREAK, completed_payloads[0].get("cycle_phase"))
        self.assertEqual(SESSIONS_PER_CYCLE, completed_payloads[0].get("session_count"))

    def test_long_break_to_work_broadcasts_work_phase_with_session_count_zero(self):
        ui, stub = self._make_ui()
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2, long_break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")
        # Advance through all sessions to reach long break
        for _ in range(SESSIONS_PER_CYCLE - 1):
            self._advance_tick(timer, cycle, ui)  # work → short_break
            self._advance_tick(timer, cycle, ui)  # short_break → work
        self._advance_tick(timer, cycle, ui)  # final work → long_break
        self.assertEqual(PHASE_TYPE_LONG_BREAK, cycle.phase_type)
        stub.events.clear()
        # Long break → work (session_count resets to 0)
        self._advance_tick(timer, cycle, ui)
        payloads = stub.pomodoro_payloads()
        completed_payloads = [p for p in payloads if p.get("action") == "completed"]
        self.assertEqual(1, len(completed_payloads))
        self.assertEqual(STATE_POMODORO_WORK, completed_payloads[0].get("cycle_phase"))
        self.assertEqual(0, completed_payloads[0].get("session_count"))

    def test_tick_event_includes_cycle_phase_when_cycle_active(self):
        ui, stub = self._make_ui()
        cycle = PomodoroCycleState()
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=25 * 60)
        timer.apply("start", session="Fokus")
        tick = timer.poll()
        self.assertFalse(tick.completed)
        handle_pomodoro_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: None,
            pomodoro_timer=timer,
            cycle=cycle,
        )
        payloads = stub.pomodoro_payloads()
        tick_payloads = [p for p in payloads if p.get("action") == "tick"]
        self.assertTrue(tick_payloads)
        last_tick = tick_payloads[-1]
        self.assertEqual(STATE_POMODORO_WORK, last_tick.get("cycle_phase"))
        self.assertEqual(0, last_tick.get("session_count"))

    def test_tick_event_includes_cycle_phase_during_short_break(self):
        ui, stub = self._make_ui()
        # Use a long break duration so the break timer is not completed on poll()
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=25 * 60)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")
        # Work → short break (resets timer to 25*60 seconds)
        self._advance_tick(timer, cycle, ui)
        self.assertEqual(PHASE_TYPE_SHORT_BREAK, cycle.phase_type)
        stub.events.clear()
        # Non-completed tick during short break
        tick = timer.poll()
        self.assertFalse(tick.completed)
        handle_pomodoro_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: None,
            pomodoro_timer=timer,
            cycle=cycle,
        )
        payloads = stub.pomodoro_payloads()
        tick_payloads = [p for p in payloads if p.get("action") == "tick"]
        self.assertTrue(tick_payloads)
        last_tick = tick_payloads[-1]
        self.assertEqual(STATE_POMODORO_SHORT_BREAK, last_tick.get("cycle_phase"))
        self.assertEqual(1, last_tick.get("session_count"))

    def test_tick_event_includes_cycle_phase_during_long_break(self):
        ui, stub = self._make_ui()
        # Use a long break duration so the long_break timer is not completed on poll()
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2, long_break_seconds=25 * 60)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")
        # Advance through all sessions to reach long break
        for _ in range(SESSIONS_PER_CYCLE - 1):
            self._advance_tick(timer, cycle, ui)  # work → short_break
            self._advance_tick(timer, cycle, ui)  # short_break → work
        self._advance_tick(timer, cycle, ui)  # final work → long_break
        self.assertEqual(PHASE_TYPE_LONG_BREAK, cycle.phase_type)
        stub.events.clear()
        # Non-completed tick during long break
        tick = timer.poll()
        self.assertFalse(tick.completed)
        handle_pomodoro_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: None,
            pomodoro_timer=timer,
            cycle=cycle,
        )
        payloads = stub.pomodoro_payloads()
        tick_payloads = [p for p in payloads if p.get("action") == "tick"]
        self.assertTrue(tick_payloads)
        last_tick = tick_payloads[-1]
        self.assertEqual(STATE_POMODORO_LONG_BREAK, last_tick.get("cycle_phase"))
        self.assertEqual(SESSIONS_PER_CYCLE, last_tick.get("session_count"))

    def test_tick_event_omits_cycle_phase_when_cycle_inactive(self):
        ui, stub = self._make_ui()
        timer = PomodoroTimer(duration_seconds=25 * 60)
        timer.apply("start", session="Fokus")
        tick = timer.poll()
        self.assertFalse(tick.completed)
        handle_pomodoro_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: None,
            pomodoro_timer=timer,
            cycle=None,
        )
        payloads = stub.pomodoro_payloads()
        self.assertTrue(payloads)
        last = payloads[-1]
        self.assertNotIn("cycle_phase", last)
        self.assertNotIn("session_count", last)


if __name__ == "__main__":
    unittest.main()

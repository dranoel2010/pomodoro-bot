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
    DEFAULT_LONG_BREAK_SECONDS,
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

from runtime.ui import RuntimeUIPublisher
from contracts.ui_protocol import EVENT_ASSISTANT_REPLY


def _make_completed_tick(timer: PomodoroTimer):
    """Fast-forward the timer to completion and return the completed tick."""
    future_time = time.monotonic() + 100_000.0
    with patch("time.monotonic", return_value=future_time):
        tick = timer.poll()
    return tick


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


class FullCycleTests(unittest.TestCase):
    def _make_ui(self):
        stub = _UIServerStub()
        return RuntimeUIPublisher(stub), stub

    def test_sessions_1_to_3_trigger_short_break_not_long_break(self) -> None:
        """Sessions 1–3 should each produce a short break, not a long break."""
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")

        for i in range(1, SESSIONS_PER_CYCLE):
            # Work session completes
            _make_completed_tick(timer)
            transition = cycle.advance(timer)
            self.assertEqual(
                PHASE_TYPE_SHORT_BREAK,
                cycle.phase_type,
                f"Session {i}: expected short_break, got {cycle.phase_type}",
            )
            self.assertEqual(PHASE_TYPE_SHORT_BREAK, transition.new_phase_type)
            self.assertEqual(i, cycle.session_count)

            # Short break completes → back to work
            _make_completed_tick(timer)
            transition = cycle.advance(timer)
            self.assertEqual(PHASE_TYPE_WORK, cycle.phase_type)
            self.assertEqual(PHASE_TYPE_WORK, transition.new_phase_type)

    def test_session_4_work_completion_triggers_long_break_not_short(self) -> None:
        """After the 4th work session, cycle transitions to long break."""
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")

        # Drive sessions 1–3 with short breaks
        for _ in range(SESSIONS_PER_CYCLE - 1):
            _make_completed_tick(timer)
            cycle.advance(timer)  # work → short_break
            _make_completed_tick(timer)
            cycle.advance(timer)  # short_break → work

        # 4th work session completes
        _make_completed_tick(timer)
        transition = cycle.advance(timer)

        self.assertEqual(PHASE_TYPE_LONG_BREAK, cycle.phase_type)
        self.assertEqual(PHASE_TYPE_LONG_BREAK, transition.new_phase_type)
        self.assertEqual(PHASE_TYPE_WORK, transition.previous_phase_type)
        self.assertEqual(SESSIONS_PER_CYCLE, cycle.session_count)

        # Timer now set to long break duration and session name
        snapshot = timer.snapshot()
        self.assertEqual("running", snapshot.phase)
        self.assertEqual("Lange Pause", snapshot.session)
        self.assertEqual(DEFAULT_LONG_BREAK_SECONDS, snapshot.duration_seconds)

    def test_long_break_completion_resets_cycle_and_returns_to_work(self) -> None:
        """Long break completion resets session_count to 0 and starts work again."""
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")

        # Drive through 4 work sessions to reach long break
        for _ in range(SESSIONS_PER_CYCLE - 1):
            _make_completed_tick(timer)
            cycle.advance(timer)  # work → short_break
            _make_completed_tick(timer)
            cycle.advance(timer)  # short_break → work
        _make_completed_tick(timer)
        cycle.advance(timer)  # work → long_break
        self.assertEqual(PHASE_TYPE_LONG_BREAK, cycle.phase_type)

        # Long break completes
        _make_completed_tick(timer)
        transition = cycle.advance(timer)

        self.assertEqual(PHASE_TYPE_WORK, cycle.phase_type)
        self.assertEqual(PHASE_TYPE_WORK, transition.new_phase_type)
        self.assertEqual(PHASE_TYPE_LONG_BREAK, transition.previous_phase_type)
        self.assertEqual(0, cycle.session_count)
        self.assertEqual(0, transition.session_count)

        # Timer session name resets to original work session name
        snapshot = timer.snapshot()
        self.assertEqual("running", snapshot.phase)
        self.assertEqual("Fokus", snapshot.session)
        self.assertEqual(2, snapshot.duration_seconds)

    def test_full_8_transition_sequence(self) -> None:
        """Full cycle: W→SB, SB→W, W→SB, SB→W, W→SB, SB→W, W→LB, LB→W."""
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")

        expected_sequence = [
            (PHASE_TYPE_SHORT_BREAK, PHASE_TYPE_WORK),   # W→SB session 1
            (PHASE_TYPE_WORK, PHASE_TYPE_SHORT_BREAK),   # SB→W
            (PHASE_TYPE_SHORT_BREAK, PHASE_TYPE_WORK),   # W→SB session 2
            (PHASE_TYPE_WORK, PHASE_TYPE_SHORT_BREAK),   # SB→W
            (PHASE_TYPE_SHORT_BREAK, PHASE_TYPE_WORK),   # W→SB session 3
            (PHASE_TYPE_WORK, PHASE_TYPE_SHORT_BREAK),   # SB→W
            (PHASE_TYPE_LONG_BREAK, PHASE_TYPE_WORK),    # W→LB session 4
            (PHASE_TYPE_WORK, PHASE_TYPE_LONG_BREAK),    # LB→W (reset)
        ]

        for idx, (expected_new, expected_prev) in enumerate(expected_sequence):
            _make_completed_tick(timer)
            transition = cycle.advance(timer)
            self.assertEqual(
                expected_new,
                transition.new_phase_type,
                f"Transition {idx + 1}: expected new={expected_new}, got {transition.new_phase_type}",
            )
            self.assertEqual(
                expected_prev,
                transition.previous_phase_type,
                f"Transition {idx + 1}: expected prev={expected_prev}, got {transition.previous_phase_type}",
            )

        self.assertEqual(0, cycle.session_count)

    def test_cycle_repeats_after_reset(self) -> None:
        """After LB→W cycle reset, session 4 again triggers a long break."""
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")

        def _drive_one_full_cycle():
            for _ in range(SESSIONS_PER_CYCLE - 1):
                _make_completed_tick(timer)
                cycle.advance(timer)  # work → short_break
                _make_completed_tick(timer)
                cycle.advance(timer)  # short_break → work
            _make_completed_tick(timer)
            cycle.advance(timer)  # work → long_break
            _make_completed_tick(timer)
            cycle.advance(timer)  # long_break → work (reset)

        # First full cycle
        _drive_one_full_cycle()
        self.assertEqual(0, cycle.session_count)
        self.assertEqual(PHASE_TYPE_WORK, cycle.phase_type)

        # Second cycle: session 4 should again trigger long break
        for _ in range(SESSIONS_PER_CYCLE - 1):
            _make_completed_tick(timer)
            transition = cycle.advance(timer)
            self.assertEqual(PHASE_TYPE_SHORT_BREAK, transition.new_phase_type)
            _make_completed_tick(timer)
            cycle.advance(timer)

        _make_completed_tick(timer)
        transition = cycle.advance(timer)
        self.assertEqual(PHASE_TYPE_LONG_BREAK, transition.new_phase_type)
        self.assertEqual(SESSIONS_PER_CYCLE, cycle.session_count)

    def test_announcement_text_non_empty_at_work_to_long_break(self) -> None:
        """Work→long break transition fires a non-empty German announcement via handle_pomodoro_tick."""
        ui, stub = self._make_ui()
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")

        # Drive to 4th work session
        for _ in range(SESSIONS_PER_CYCLE - 1):
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

        # 4th work session completion
        stub.events.clear()
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

        self.assertEqual(PHASE_TYPE_LONG_BREAK, cycle.phase_type)
        assistant_events = [p for kind, p in stub.events if kind == EVENT_ASSISTANT_REPLY]
        self.assertEqual(1, len(assistant_events))
        text = assistant_events[0].get("text", "")
        self.assertTrue(text, "Expected non-empty long break announcement")
        self.assertIn("Lange Pause", text)
        self.assertIn("15 Minuten", text)
        self.assertIn("Gut gemacht", text)

    def test_announcement_text_non_empty_at_long_break_to_work(self) -> None:
        """Long break→work cycle reset fires a non-empty German announcement."""
        ui, stub = self._make_ui()
        cycle = PomodoroCycleState(work_seconds=2, break_seconds=2)
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")

        # Drive to long break
        for _ in range(SESSIONS_PER_CYCLE - 1):
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
        self.assertEqual(PHASE_TYPE_LONG_BREAK, cycle.phase_type)

        # Long break completes
        stub.events.clear()
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

        self.assertEqual(PHASE_TYPE_WORK, cycle.phase_type)
        self.assertEqual(0, cycle.session_count)
        assistant_events = [p for kind, p in stub.events if kind == EVENT_ASSISTANT_REPLY]
        self.assertEqual(1, len(assistant_events))
        text = assistant_events[0].get("text", "")
        self.assertTrue(text, "Expected non-empty cycle reset announcement")
        self.assertIn("Lange Pause vorbei", text)
        self.assertIn("Neuer Zyklus", text)


if __name__ == "__main__":
    unittest.main()

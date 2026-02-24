import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from pomodoro import PomodoroSnapshot, PomodoroTick

# Import runtime.ticks without executing src/runtime/__init__.py.
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg


def _build_tts_stub():
    module = types.ModuleType("tts")

    class TTSError(Exception):
        pass

    class SpeechService:  # pragma: no cover - type placeholder
        pass

    module.TTSError = TTSError
    module.SpeechService = SpeechService
    return module


with patch.dict(sys.modules, {"tts": _build_tts_stub()}):
    from runtime.ticks import handle_pomodoro_tick, handle_timer_tick


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


class TickStateFlowTests(unittest.TestCase):
    def test_timer_completion_publishes_replying_then_idle(self) -> None:
        ui = _UIServerStub()
        idle_calls: list[str] = []
        tick = PomodoroTick(
            snapshot=PomodoroSnapshot(
                phase="completed",
                session="Timer",
                duration_seconds=10 * 60,
                remaining_seconds=0,
            ),
            completed=True,
        )

        handle_timer_tick(
            tick,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            publish_idle_state=lambda: idle_calls.append("idle"),
        )

        self.assertIn(("replying", "Timer completed", {}), ui.states)
        assistant_events = [payload for kind, payload in ui.events if kind == "assistant_reply"]
        self.assertEqual(1, len(assistant_events))
        self.assertNotIn("state", assistant_events[0])
        self.assertEqual(["idle"], idle_calls)
        self.assertLess(
            ui.trace.index(("state", "replying")),
            ui.trace.index(("event", "assistant_reply")),
        )

    def test_pomodoro_completion_publishes_replying_then_idle(self) -> None:
        ui = _UIServerStub()
        idle_calls: list[str] = []
        tick = PomodoroTick(
            snapshot=PomodoroSnapshot(
                phase="completed",
                session="Deep work",
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
        )

        self.assertIn(("replying", "Pomodoro completed", {}), ui.states)
        assistant_events = [payload for kind, payload in ui.events if kind == "assistant_reply"]
        self.assertEqual(1, len(assistant_events))
        self.assertNotIn("state", assistant_events[0])
        self.assertEqual(["idle"], idle_calls)
        self.assertLess(
            ui.trace.index(("state", "replying")),
            ui.trace.index(("event", "assistant_reply")),
        )


if __name__ == "__main__":
    unittest.main()

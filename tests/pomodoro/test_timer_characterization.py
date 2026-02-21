import unittest
from unittest.mock import patch

from pomodoro.service import PomodoroTimer


class PomodoroTimerCharacterizationTests(unittest.TestCase):
    def test_start_sets_running_with_duration(self) -> None:
        timer = PomodoroTimer(duration_seconds=10)
        with patch("pomodoro.service.time.monotonic", side_effect=[100.0]):
            result = timer.apply("start", session="Focus")

        self.assertTrue(result.accepted)
        self.assertEqual("running", result.snapshot.phase)
        self.assertEqual(10, result.snapshot.duration_seconds)
        self.assertEqual(10, result.snapshot.remaining_seconds)

    def test_pause_rejected_when_not_running(self) -> None:
        timer = PomodoroTimer(duration_seconds=10)
        result = timer.apply("pause")
        self.assertFalse(result.accepted)
        self.assertEqual("not_running", result.reason)

    def test_continue_rejected_when_not_paused(self) -> None:
        timer = PomodoroTimer(duration_seconds=10)
        with patch("pomodoro.service.time.monotonic", side_effect=[100.0, 101.0]):
            timer.apply("start", session="Focus")
            result = timer.apply("continue")
        self.assertFalse(result.accepted)
        self.assertEqual("not_paused", result.reason)

    def test_abort_rejected_when_not_active(self) -> None:
        timer = PomodoroTimer(duration_seconds=10)
        result = timer.apply("abort")
        self.assertFalse(result.accepted)
        self.assertEqual("not_active", result.reason)

    def test_pause_then_continue_preserves_remaining(self) -> None:
        timer = PomodoroTimer(duration_seconds=10)
        with patch(
            "pomodoro.service.time.monotonic",
            side_effect=[100.0, 103.0, 108.0],
        ):
            timer.apply("start", session="Focus")
            pause_result = timer.apply("pause")
            continue_result = timer.apply("continue")

        self.assertTrue(pause_result.accepted)
        self.assertEqual(7, pause_result.snapshot.remaining_seconds)
        self.assertTrue(continue_result.accepted)
        self.assertEqual(7, continue_result.snapshot.remaining_seconds)

    def test_poll_emits_tick_once_per_second_and_completion(self) -> None:
        timer = PomodoroTimer(duration_seconds=3)
        with patch(
            "pomodoro.service.time.monotonic",
            side_effect=[100.0, 100.0, 101.0, 102.0, 103.0],
        ):
            timer.apply("start", session="Focus")
            tick_1 = timer.poll()
            tick_2 = timer.poll()
            tick_3 = timer.poll()
            tick_4 = timer.poll()

        self.assertIsNotNone(tick_1)
        self.assertIsNotNone(tick_2)
        self.assertIsNotNone(tick_3)
        self.assertIsNotNone(tick_4)
        if tick_1 is None or tick_2 is None or tick_3 is None or tick_4 is None:
            self.fail("Expected all poll calls to return tick payloads")
        self.assertEqual(3, tick_1.snapshot.remaining_seconds)
        self.assertEqual(2, tick_2.snapshot.remaining_seconds)
        self.assertEqual(1, tick_3.snapshot.remaining_seconds)
        self.assertEqual(0, tick_4.snapshot.remaining_seconds)
        self.assertFalse(tick_1.completed)
        self.assertFalse(tick_2.completed)
        self.assertFalse(tick_3.completed)
        self.assertTrue(tick_4.completed)
        self.assertEqual("completed", tick_4.snapshot.phase)

    def test_reset_restarts_timer(self) -> None:
        timer = PomodoroTimer(duration_seconds=10)
        with patch(
            "pomodoro.service.time.monotonic",
            side_effect=[100.0, 102.0, 103.0],
        ):
            timer.apply("start", session="Focus")
            timer.poll()
            reset_result = timer.apply("reset")

        self.assertTrue(reset_result.accepted)
        self.assertEqual("running", reset_result.snapshot.phase)
        self.assertEqual(10, reset_result.snapshot.remaining_seconds)

    def test_session_name_is_sanitized(self) -> None:
        timer = PomodoroTimer(duration_seconds=10)
        raw_session = "   This    is      a   very very very very very very long session name    "
        with patch("pomodoro.service.time.monotonic", side_effect=[100.0]):
            result = timer.apply("start", session=raw_session)

        session = result.snapshot.session or ""
        self.assertTrue(session)
        self.assertLessEqual(len(session), 60)
        self.assertEqual(" ".join(session.split()), session)


if __name__ == "__main__":
    unittest.main()

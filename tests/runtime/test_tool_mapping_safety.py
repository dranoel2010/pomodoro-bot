import unittest

from pomodoro.tool_mapping import remap_timer_tool_for_active_pomodoro


class ToolMappingSafetyTests(unittest.TestCase):
    def test_active_pomodoro_maps_start_timer(self) -> None:
        self.assertEqual(
            "start_pomodoro_session",
            remap_timer_tool_for_active_pomodoro(
                "start_timer", pomodoro_active=True
            ),
        )

    def test_active_pomodoro_maps_pause_timer(self) -> None:
        self.assertEqual(
            "pause_pomodoro_session",
            remap_timer_tool_for_active_pomodoro(
                "pause_timer", pomodoro_active=True
            ),
        )

    def test_active_pomodoro_maps_continue_timer(self) -> None:
        self.assertEqual(
            "continue_pomodoro_session",
            remap_timer_tool_for_active_pomodoro(
                "continue_timer", pomodoro_active=True
            ),
        )

    def test_active_pomodoro_maps_stop_timer(self) -> None:
        self.assertEqual(
            "stop_pomodoro_session",
            remap_timer_tool_for_active_pomodoro("stop_timer", pomodoro_active=True),
        )

    def test_active_pomodoro_maps_reset_timer(self) -> None:
        self.assertEqual(
            "reset_pomodoro_session",
            remap_timer_tool_for_active_pomodoro("reset_timer", pomodoro_active=True),
        )

    def test_inactive_pomodoro_leaves_timer_tools_unchanged(self) -> None:
        self.assertEqual(
            "start_timer",
            remap_timer_tool_for_active_pomodoro(
                "start_timer", pomodoro_active=False
            ),
        )

    def test_non_timer_tools_unchanged(self) -> None:
        self.assertEqual(
            "show_upcoming_events",
            remap_timer_tool_for_active_pomodoro(
                "show_upcoming_events", pomodoro_active=True
            ),
        )
        self.assertEqual(
            "add_calendar_event",
            remap_timer_tool_for_active_pomodoro(
                "add_calendar_event", pomodoro_active=True
            ),
        )


if __name__ == "__main__":
    unittest.main()

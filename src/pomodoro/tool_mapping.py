from __future__ import annotations


def remap_timer_tool_for_active_pomodoro(tool_name: str, *, pomodoro_active: bool) -> str:
    """Map timer tools to pomodoro tools while a pomodoro session is active."""
    if pomodoro_active:
        return tool_name.replace("_timer", "_pomodoro_session")
    return tool_name

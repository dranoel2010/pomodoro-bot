"""Runtime helper for remapping timer tools during active pomodoro sessions."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _timer_to_pomodoro_tool() -> dict[str, str]:
    # Lazy import avoids package init cycle: tool_contract -> pomodoro.constants
    # -> pomodoro package -> tool_mapping.
    from contracts.tool_contract import (
        TOOL_CONTINUE_POMODORO,
        TOOL_CONTINUE_TIMER,
        TOOL_PAUSE_POMODORO,
        TOOL_PAUSE_TIMER,
        TOOL_RESET_POMODORO,
        TOOL_RESET_TIMER,
        TOOL_START_POMODORO,
        TOOL_START_TIMER,
        TOOL_STOP_POMODORO,
        TOOL_STOP_TIMER,
    )

    return {
        TOOL_START_TIMER: TOOL_START_POMODORO,
        TOOL_PAUSE_TIMER: TOOL_PAUSE_POMODORO,
        TOOL_CONTINUE_TIMER: TOOL_CONTINUE_POMODORO,
        TOOL_STOP_TIMER: TOOL_STOP_POMODORO,
        TOOL_RESET_TIMER: TOOL_RESET_POMODORO,
    }


def remap_timer_tool_for_active_pomodoro(tool_name: str, *, pomodoro_active: bool) -> str:
    """Map timer tools to pomodoro tools while a pomodoro session is active."""
    if pomodoro_active:
        return _timer_to_pomodoro_tool().get(tool_name, tool_name)
    return tool_name

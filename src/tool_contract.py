from __future__ import annotations

# Canonical tool names used by parser, runtime dispatch, and LLM grammar.
TOOL_NAME_ORDER: tuple[str, ...] = (
    "start_timer",
    "stop_timer",
    "pause_timer",
    "continue_timer",
    "reset_timer",
    "start_pomodoro_session",
    "stop_pomodoro_session",
    "pause_pomodoro_session",
    "continue_pomodoro_session",
    "reset_pomodoro_session",
    "show_upcoming_events",
    "add_calendar_event",
)

TOOL_NAMES: frozenset[str] = frozenset(TOOL_NAME_ORDER)

TIMER_TOOL_TO_RUNTIME_ACTION: dict[str, str] = {
    "start_timer": "start",
    "pause_timer": "pause",
    "continue_timer": "continue",
    "stop_timer": "abort",
    "reset_timer": "reset",
}

POMODORO_TOOL_TO_RUNTIME_ACTION: dict[str, str] = {
    "start_pomodoro_session": "start",
    "pause_pomodoro_session": "pause",
    "continue_pomodoro_session": "continue",
    "stop_pomodoro_session": "abort",
    "reset_pomodoro_session": "reset",
}

INTENT_TO_TIMER_TOOL: dict[str, str] = {
    "start": "start_timer",
    "pause": "pause_timer",
    "continue": "continue_timer",
    "stop": "stop_timer",
    "reset": "reset_timer",
}

INTENT_TO_POMODORO_TOOL: dict[str, str] = {
    "start": "start_pomodoro_session",
    "pause": "pause_pomodoro_session",
    "continue": "continue_pomodoro_session",
    "stop": "stop_pomodoro_session",
    "reset": "reset_pomodoro_session",
}

CALENDAR_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "show_upcoming_events",
        "add_calendar_event",
    }
)


def tool_names_one_of_csv() -> str:
    """Return tool names as `a,b,c` for prompt snippets."""
    return ",".join(TOOL_NAME_ORDER)


def tool_name_gbnf_alternatives() -> str:
    """Return grammar alternatives for the tool-name non-terminal."""
    return " | ".join(f'"\\\"{name}\\\""' for name in TOOL_NAME_ORDER)

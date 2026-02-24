"""Canonical tool names and intent mappings for parser and runtime."""

from __future__ import annotations

from pomodoro.constants import (
    ACTION_ABORT,
    ACTION_CONTINUE,
    ACTION_PAUSE,
    ACTION_RESET,
    ACTION_START,
)

INTENT_STOP = "stop"

# Canonical tool names used by parser, runtime dispatch, and LLM grammar.
TOOL_START_TIMER = "start_timer"
TOOL_STOP_TIMER = "stop_timer"
TOOL_PAUSE_TIMER = "pause_timer"
TOOL_CONTINUE_TIMER = "continue_timer"
TOOL_RESET_TIMER = "reset_timer"

TOOL_START_POMODORO = "start_pomodoro_session"
TOOL_STOP_POMODORO = "stop_pomodoro_session"
TOOL_PAUSE_POMODORO = "pause_pomodoro_session"
TOOL_CONTINUE_POMODORO = "continue_pomodoro_session"
TOOL_RESET_POMODORO = "reset_pomodoro_session"

TOOL_SHOW_UPCOMING_EVENTS = "show_upcoming_events"
TOOL_ADD_CALENDAR_EVENT = "add_calendar_event"

# Canonical tool names used by parser, runtime dispatch, and LLM grammar.
TOOL_NAME_ORDER: tuple[str, ...] = (
    TOOL_START_TIMER,
    TOOL_STOP_TIMER,
    TOOL_PAUSE_TIMER,
    TOOL_CONTINUE_TIMER,
    TOOL_RESET_TIMER,
    TOOL_START_POMODORO,
    TOOL_STOP_POMODORO,
    TOOL_PAUSE_POMODORO,
    TOOL_CONTINUE_POMODORO,
    TOOL_RESET_POMODORO,
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_ADD_CALENDAR_EVENT,
)

TOOL_NAMES: frozenset[str] = frozenset(TOOL_NAME_ORDER)

TIMER_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_START_TIMER,
        TOOL_STOP_TIMER,
        TOOL_PAUSE_TIMER,
        TOOL_CONTINUE_TIMER,
        TOOL_RESET_TIMER,
    }
)

POMODORO_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_START_POMODORO,
        TOOL_STOP_POMODORO,
        TOOL_PAUSE_POMODORO,
        TOOL_CONTINUE_POMODORO,
        TOOL_RESET_POMODORO,
    }
)

TOOLS_WITHOUT_ARGUMENTS: frozenset[str] = frozenset(
    {
        TOOL_STOP_TIMER,
        TOOL_PAUSE_TIMER,
        TOOL_CONTINUE_TIMER,
        TOOL_RESET_TIMER,
        TOOL_STOP_POMODORO,
        TOOL_PAUSE_POMODORO,
        TOOL_CONTINUE_POMODORO,
        TOOL_RESET_POMODORO,
    }
)

TIMER_TOOL_TO_RUNTIME_ACTION: dict[str, str] = {
    TOOL_START_TIMER: ACTION_START,
    TOOL_PAUSE_TIMER: ACTION_PAUSE,
    TOOL_CONTINUE_TIMER: ACTION_CONTINUE,
    TOOL_STOP_TIMER: ACTION_ABORT,
    TOOL_RESET_TIMER: ACTION_RESET,
}

POMODORO_TOOL_TO_RUNTIME_ACTION: dict[str, str] = {
    TOOL_START_POMODORO: ACTION_START,
    TOOL_PAUSE_POMODORO: ACTION_PAUSE,
    TOOL_CONTINUE_POMODORO: ACTION_CONTINUE,
    TOOL_STOP_POMODORO: ACTION_ABORT,
    TOOL_RESET_POMODORO: ACTION_RESET,
}

INTENT_TO_TIMER_TOOL: dict[str, str] = {
    ACTION_START: TOOL_START_TIMER,
    ACTION_PAUSE: TOOL_PAUSE_TIMER,
    ACTION_CONTINUE: TOOL_CONTINUE_TIMER,
    INTENT_STOP: TOOL_STOP_TIMER,
    ACTION_RESET: TOOL_RESET_TIMER,
}

INTENT_TO_POMODORO_TOOL: dict[str, str] = {
    ACTION_START: TOOL_START_POMODORO,
    ACTION_PAUSE: TOOL_PAUSE_POMODORO,
    ACTION_CONTINUE: TOOL_CONTINUE_POMODORO,
    INTENT_STOP: TOOL_STOP_POMODORO,
    ACTION_RESET: TOOL_RESET_POMODORO,
}

CALENDAR_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_SHOW_UPCOMING_EVENTS,
        TOOL_ADD_CALENDAR_EVENT,
    }
)


def tool_names_one_of_csv() -> str:
    """Return tool names as `a,b,c` for prompt snippets."""
    return ",".join(TOOL_NAME_ORDER)


def tool_name_gbnf_alternatives() -> str:
    """Return grammar alternatives for the tool-name non-terminal."""
    return " | ".join(f'"\\\"{name}\\\""' for name in TOOL_NAME_ORDER)

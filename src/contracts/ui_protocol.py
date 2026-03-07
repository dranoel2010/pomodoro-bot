"""Web UI websocket event and state constants."""

from __future__ import annotations

from enum import StrEnum


class UIEvent(StrEnum):
    HELLO = "hello"
    STATE_UPDATE = "state_update"
    POMODORO = "pomodoro"
    TIMER = "timer"
    TRANSCRIPT = "transcript"
    ASSISTANT_REPLY = "assistant_reply"
    ERROR = "error"


class AppState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    REPLYING = "replying"
    ERROR = "error"


class PomodoroPhaseState(StrEnum):
    WORK = "pomodoro_work"
    SHORT_BREAK = "pomodoro_short_break"
    LONG_BREAK = "pomodoro_long_break"
    IDLE = "pomodoro_idle"


# Websocket event types
EVENT_HELLO = UIEvent.HELLO
EVENT_STATE_UPDATE = UIEvent.STATE_UPDATE
EVENT_POMODORO = UIEvent.POMODORO
EVENT_TIMER = UIEvent.TIMER
EVENT_TRANSCRIPT = UIEvent.TRANSCRIPT
EVENT_ASSISTANT_REPLY = UIEvent.ASSISTANT_REPLY
EVENT_ERROR = UIEvent.ERROR

# UI runtime states
STATE_IDLE = AppState.IDLE
STATE_LISTENING = AppState.LISTENING
STATE_TRANSCRIBING = AppState.TRANSCRIBING
STATE_THINKING = AppState.THINKING
STATE_REPLYING = AppState.REPLYING
STATE_ERROR = AppState.ERROR

# Pomodoro cycle phase states (distinct from AppState — tracks the cycle phase, not pipeline state)
STATE_POMODORO_WORK = PomodoroPhaseState.WORK
STATE_POMODORO_SHORT_BREAK = PomodoroPhaseState.SHORT_BREAK
STATE_POMODORO_LONG_BREAK = PomodoroPhaseState.LONG_BREAK
STATE_POMODORO_IDLE = PomodoroPhaseState.IDLE

STICKY_EVENT_TYPES: frozenset[str] = frozenset(
    {
        EVENT_STATE_UPDATE,
        EVENT_POMODORO,
        EVENT_TIMER,
        EVENT_TRANSCRIPT,
        EVENT_ASSISTANT_REPLY,
        EVENT_ERROR,
    }
)

STICKY_EVENT_ORDER: tuple[str, ...] = (
    EVENT_POMODORO,
    EVENT_TIMER,
    EVENT_TRANSCRIPT,
    EVENT_ASSISTANT_REPLY,
    EVENT_ERROR,
    EVENT_STATE_UPDATE,
)

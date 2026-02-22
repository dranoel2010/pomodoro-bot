"""Web UI websocket event and state constants."""

from __future__ import annotations

# Websocket event types
EVENT_HELLO = "hello"
EVENT_STATE_UPDATE = "state_update"
EVENT_POMODORO = "pomodoro"
EVENT_TIMER = "timer"
EVENT_TRANSCRIPT = "transcript"
EVENT_ASSISTANT_REPLY = "assistant_reply"
EVENT_ERROR = "error"

# UI runtime states
STATE_IDLE = "idle"
STATE_LISTENING = "listening"
STATE_TRANSCRIBING = "transcribing"
STATE_THINKING = "thinking"
STATE_REPLYING = "replying"
STATE_ERROR = "error"

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

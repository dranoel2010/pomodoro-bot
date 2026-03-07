"""State, action, and reason constants used by pomodoro runtime logic."""

from __future__ import annotations

DEFAULT_POMODORO_SECONDS = 25 * 60
DEFAULT_POMODORO_SESSION_NAME = "Focus"
DEFAULT_SHORT_BREAK_SECONDS = 5 * 60
DEFAULT_SHORT_BREAK_SESSION_NAME = "Kurze Pause"

PHASE_TYPE_WORK = "work"
PHASE_TYPE_SHORT_BREAK = "short_break"
PHASE_TYPE_LONG_BREAK = "long_break"

DEFAULT_LONG_BREAK_SECONDS = 15 * 60
DEFAULT_LONG_BREAK_SESSION_NAME = "Lange Pause"
SESSIONS_PER_CYCLE = 4

PHASE_IDLE = "idle"
PHASE_RUNNING = "running"
PHASE_PAUSED = "paused"
PHASE_COMPLETED = "completed"
PHASE_ABORTED = "aborted"

ACTIVE_PHASES: frozenset[str] = frozenset({PHASE_RUNNING, PHASE_PAUSED})

ACTION_START = "start"
ACTION_PAUSE = "pause"
ACTION_CONTINUE = "continue"
ACTION_ABORT = "abort"
ACTION_RESET = "reset"

ACTION_SYNC = "sync"
ACTION_TICK = "tick"
ACTION_COMPLETED = "completed"

REASON_STARTED = "started"
REASON_RESET = "reset"
REASON_PAUSED = "paused"
REASON_CONTINUED = "continued"
REASON_ABORTED = "aborted"
REASON_NOT_RUNNING = "not_running"
REASON_NOT_PAUSED = "not_paused"
REASON_NOT_ACTIVE = "not_active"
REASON_INVALID_STATE = "invalid_state"
REASON_UNSUPPORTED_ACTION = "unsupported_action"

REASON_TIMER_ACTIVE = "timer_active"
REASON_POMODORO_ACTIVE = "pomodoro_active"
REASON_SUPERSEDED_BY_POMODORO = "superseded_by_pomodoro"
REASON_TICK = "tick"
REASON_COMPLETED = "completed"
REASON_STARTUP = "startup"

"""German status and fallback response text builders for timer flows."""

from __future__ import annotations

from shared.defaults import DEFAULT_FOCUS_TOPIC_DE
from pomodoro import PomodoroSnapshot
from pomodoro.constants import (
    ACTION_ABORT,
    ACTION_COMPLETED,
    ACTION_CONTINUE,
    ACTION_PAUSE,
    ACTION_RESET,
    ACTION_START,
    ACTIVE_PHASES,
    PHASE_ABORTED,
    PHASE_COMPLETED,
    PHASE_PAUSED,
    PHASE_RUNNING,
    REASON_NOT_ACTIVE,
    REASON_NOT_PAUSED,
    REASON_NOT_RUNNING,
    REASON_POMODORO_ACTIVE,
    REASON_TIMER_ACTIVE,
)

ACTIVE_SESSION_PHASES: set[str] = set(ACTIVE_PHASES)


def format_duration(seconds: int) -> str:
    """Format a duration in seconds as `MM:SS`."""
    minutes, remainder = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def timer_status_message(snapshot: PomodoroSnapshot) -> str:
    """Build timer status text for the current timer snapshot."""
    if snapshot.phase == PHASE_RUNNING:
        return f"Timer laeuft ({format_duration(snapshot.remaining_seconds)} verbleibend)"
    if snapshot.phase == PHASE_PAUSED:
        return f"Timer pausiert ({format_duration(snapshot.remaining_seconds)} verbleibend)"
    if snapshot.phase == PHASE_COMPLETED:
        return "Timer abgeschlossen"
    if snapshot.phase == PHASE_ABORTED:
        return "Timer gestoppt"
    return "Bereit"


def pomodoro_status_message(snapshot: PomodoroSnapshot) -> str:
    """Build pomodoro status text for the current session snapshot."""
    if snapshot.phase == PHASE_RUNNING:
        return (
            f"Pomodoro '{snapshot.session or DEFAULT_FOCUS_TOPIC_DE}' laeuft "
            f"({format_duration(snapshot.remaining_seconds)} verbleibend)"
        )
    if snapshot.phase == PHASE_PAUSED:
        return (
            f"Pomodoro '{snapshot.session or DEFAULT_FOCUS_TOPIC_DE}' pausiert "
            f"({format_duration(snapshot.remaining_seconds)} verbleibend)"
        )
    if snapshot.phase == PHASE_COMPLETED:
        return f"Pomodoro '{snapshot.session or DEFAULT_FOCUS_TOPIC_DE}' abgeschlossen"
    if snapshot.phase == PHASE_ABORTED:
        return f"Pomodoro '{snapshot.session or DEFAULT_FOCUS_TOPIC_DE}' gestoppt"
    return "Bereit"


def default_pomodoro_text(action: str, snapshot: PomodoroSnapshot) -> str:
    """Return default German text for accepted pomodoro actions."""
    topic = snapshot.session or DEFAULT_FOCUS_TOPIC_DE
    if action == ACTION_START:
        return f"Ich starte jetzt deine Pomodoro Sitzung fuer {topic}."
    if action == ACTION_CONTINUE:
        return f"Ich setze die Pomodoro Sitzung fuer {topic} fort."
    if action == ACTION_PAUSE:
        return f"Ich pausiere die Pomodoro Sitzung fuer {topic}."
    if action == ACTION_ABORT:
        return f"Ich stoppe die Pomodoro Sitzung fuer {topic}."
    if action == ACTION_COMPLETED:
        return f"Pomodoro abgeschlossen. Gute Arbeit bei {topic}."
    return f"Pomodoro aktualisiert: {topic}."


def pomodoro_rejection_text(action: str, reason: str) -> str:
    """Return German rejection text for unsupported pomodoro actions."""
    if reason == REASON_TIMER_ACTIVE:
        return "Es laeuft bereits ein Timer. Bitte stoppe den Timer zuerst."
    if reason == REASON_NOT_RUNNING and action == ACTION_PAUSE:
        return "Die Pomodoro Sitzung laeuft gerade nicht."
    if reason == REASON_NOT_PAUSED and action == ACTION_CONTINUE:
        return "Die Pomodoro Sitzung ist nicht pausiert."
    if reason == REASON_NOT_ACTIVE and action == ACTION_ABORT:
        return "Es gibt keine aktive Pomodoro Sitzung."
    return "Die Pomodoro Aktion ist im aktuellen Zustand nicht moeglich."


def default_timer_text(action: str, snapshot: PomodoroSnapshot) -> str:
    """Return default German text for accepted timer actions."""
    if action == ACTION_START:
        return f"Ich starte den Timer mit {format_duration(snapshot.duration_seconds)}."
    if action == ACTION_CONTINUE:
        return "Ich setze den Timer fort."
    if action == ACTION_PAUSE:
        return "Ich pausiere den Timer."
    if action == ACTION_ABORT:
        return "Ich stoppe den Timer."
    if action == ACTION_RESET:
        return "Ich setze den Timer zurueck."
    if action == ACTION_COMPLETED:
        return "Der Timer ist abgelaufen."
    return "Timer aktualisiert."


def timer_rejection_text(action: str, reason: str) -> str:
    """Return German rejection text for unsupported timer actions."""
    if reason == REASON_POMODORO_ACTIVE:
        return "Es laeuft bereits eine Pomodoro Sitzung. Bitte stoppe sie zuerst."
    if reason == REASON_NOT_RUNNING and action == ACTION_PAUSE:
        return "Der Timer laeuft gerade nicht."
    if reason == REASON_NOT_PAUSED and action == ACTION_CONTINUE:
        return "Der Timer ist nicht pausiert."
    if reason == REASON_NOT_ACTIVE and action == ACTION_ABORT:
        return "Es gibt keinen aktiven Timer."
    return "Die Timer Aktion ist im aktuellen Zustand nicht moeglich."

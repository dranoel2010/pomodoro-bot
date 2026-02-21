from __future__ import annotations

from pomodoro import PomodoroSnapshot

ACTIVE_SESSION_PHASES: set[str] = {"running", "paused"}


def format_duration(seconds: int) -> str:
    minutes, remainder = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def timer_status_message(snapshot: PomodoroSnapshot) -> str:
    if snapshot.phase == "running":
        return f"Timer laeuft ({format_duration(snapshot.remaining_seconds)} verbleibend)"
    if snapshot.phase == "paused":
        return f"Timer pausiert ({format_duration(snapshot.remaining_seconds)} verbleibend)"
    if snapshot.phase == "completed":
        return "Timer abgeschlossen"
    if snapshot.phase == "aborted":
        return "Timer gestoppt"
    return "Bereit"


def pomodoro_status_message(snapshot: PomodoroSnapshot) -> str:
    if snapshot.phase == "running":
        return (
            f"Pomodoro '{snapshot.session or 'Fokus'}' laeuft "
            f"({format_duration(snapshot.remaining_seconds)} verbleibend)"
        )
    if snapshot.phase == "paused":
        return (
            f"Pomodoro '{snapshot.session or 'Fokus'}' pausiert "
            f"({format_duration(snapshot.remaining_seconds)} verbleibend)"
        )
    if snapshot.phase == "completed":
        return f"Pomodoro '{snapshot.session or 'Fokus'}' abgeschlossen"
    if snapshot.phase == "aborted":
        return f"Pomodoro '{snapshot.session or 'Fokus'}' gestoppt"
    return "Bereit"


def default_pomodoro_text(action: str, snapshot: PomodoroSnapshot) -> str:
    topic = snapshot.session or "Fokus"
    if action == "start":
        return f"Ich starte jetzt deine Pomodoro Sitzung fuer {topic}."
    if action == "continue":
        return f"Ich setze die Pomodoro Sitzung fuer {topic} fort."
    if action == "pause":
        return f"Ich pausiere die Pomodoro Sitzung fuer {topic}."
    if action == "abort":
        return f"Ich stoppe die Pomodoro Sitzung fuer {topic}."
    if action == "completed":
        return f"Pomodoro abgeschlossen. Gute Arbeit bei {topic}."
    return f"Pomodoro aktualisiert: {topic}."


def pomodoro_rejection_text(action: str, reason: str) -> str:
    if reason == "timer_active":
        return "Es laeuft bereits ein Timer. Bitte stoppe den Timer zuerst."
    if reason == "not_running" and action == "pause":
        return "Die Pomodoro Sitzung laeuft gerade nicht."
    if reason == "not_paused" and action == "continue":
        return "Die Pomodoro Sitzung ist nicht pausiert."
    if reason == "not_active" and action == "abort":
        return "Es gibt keine aktive Pomodoro Sitzung."
    return "Die Pomodoro Aktion ist im aktuellen Zustand nicht moeglich."


def default_timer_text(action: str, snapshot: PomodoroSnapshot) -> str:
    if action == "start":
        return f"Ich starte den Timer mit {format_duration(snapshot.duration_seconds)}."
    if action == "continue":
        return "Ich setze den Timer fort."
    if action == "pause":
        return "Ich pausiere den Timer."
    if action == "abort":
        return "Ich stoppe den Timer."
    if action == "reset":
        return "Ich setze den Timer zurueck."
    if action == "completed":
        return "Der Timer ist abgelaufen."
    return "Timer aktualisiert."


def timer_rejection_text(action: str, reason: str) -> str:
    if reason == "pomodoro_active":
        return "Es laeuft bereits eine Pomodoro Sitzung. Bitte stoppe sie zuerst."
    if reason == "not_running" and action == "pause":
        return "Der Timer laeuft gerade nicht."
    if reason == "not_paused" and action == "continue":
        return "Der Timer ist nicht pausiert."
    if reason == "not_active" and action == "abort":
        return "Es gibt keinen aktiven Timer."
    return "Die Timer Aktion ist im aktuellen Zustand nicht moeglich."

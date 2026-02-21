from __future__ import annotations

import re
from typing import Optional

from .types import ToolCall


def normalize_assistant_text(text: str, tool_call: Optional[ToolCall]) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return fallback_assistant_text(tool_call)
    if normalized.lower() in {"ok", "okay", "klar", "verstanden"} and tool_call is not None:
        return fallback_assistant_text(tool_call)
    if is_probably_english(normalized):
        return fallback_assistant_text(tool_call)
    return normalized


def is_probably_english(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"^\s*(sure|okay|i can|let me|here is)\b", lowered):
        return True

    english_hits = len(
        re.findall(
            r"\b(the|and|you|your|what|should|sorry|could|please|hello|thanks|let|lets|sure|okay|can|is|are|was|were|has|have|been|will|started|starting|paused|running)\b",
            lowered,
        )
    )
    german_hits = len(
        re.findall(
            r"\b(ich|du|dein|deine|bitte|heute|timer|sitzung|fokus|starten|pausieren|fortsetzen|abbrechen|ja|nein|gern|klar)\b",
            lowered,
        )
    )
    has_umlaut = bool(re.search(r"[äöüß]", lowered))
    return english_hits >= 2 and english_hits >= (german_hits + 1) and not has_umlaut


def fallback_assistant_text(tool_call: Optional[ToolCall]) -> str:
    if tool_call is None:
        return "Bitte formuliere die Anfrage auf Deutsch und etwas genauer."

    name = tool_call["name"]
    if name == "start_timer":
        duration = tool_call["arguments"].get("duration", "10")
        return f"Ich starte den Timer mit der Dauer {duration}."
    if name == "stop_timer":
        return "Ich stoppe den laufenden Timer."
    if name == "pause_timer":
        return "Ich pausiere den Timer."
    if name == "continue_timer":
        return "Ich setze den Timer fort."
    if name == "reset_timer":
        return "Ich setze den Timer zurueck."
    if name == "start_pomodoro_session":
        topic = tool_call["arguments"].get("focus_topic", "Fokus")
        return f"Ich starte eine Pomodoro Sitzung fuer {topic}."
    if name == "stop_pomodoro_session":
        return "Ich stoppe die aktuelle Pomodoro Sitzung."
    if name == "pause_pomodoro_session":
        return "Ich pausiere die Pomodoro Sitzung."
    if name == "continue_pomodoro_session":
        return "Ich setze die Pomodoro Sitzung fort."
    if name == "reset_pomodoro_session":
        return "Ich setze die Pomodoro Sitzung zurueck."
    if name == "show_upcoming_events":
        return "Ich zeige die anstehenden Termine im gewuenschten Zeitraum."
    if name == "add_calendar_event":
        return "Ich lege den Kalendereintrag an."
    return "Anfrage verarbeitet."

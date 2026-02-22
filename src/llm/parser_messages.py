"""Assistant message normalization and deterministic fallback replies."""

from __future__ import annotations

import re
from typing import Optional

from shared.defaults import DEFAULT_FOCUS_TOPIC_DE, DEFAULT_TIMER_MINUTES
from contracts.tool_contract import (
    TOOL_ADD_CALENDAR_EVENT,
    TOOL_CONTINUE_POMODORO,
    TOOL_CONTINUE_TIMER,
    TOOL_PAUSE_POMODORO,
    TOOL_PAUSE_TIMER,
    TOOL_RESET_POMODORO,
    TOOL_RESET_TIMER,
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_START_POMODORO,
    TOOL_START_TIMER,
    TOOL_STOP_POMODORO,
    TOOL_STOP_TIMER,
)

from .types import ToolCall


def normalize_assistant_text(text: str, tool_call: Optional[ToolCall]) -> str:
    """Normalize assistant text and replace weak replies with deterministic fallbacks."""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return fallback_assistant_text(tool_call)
    if normalized.lower() in {"ok", "okay", "klar", "verstanden"} and tool_call is not None:
        return fallback_assistant_text(tool_call)
    if is_probably_english(normalized):
        return fallback_assistant_text(tool_call)
    return normalized


def is_probably_english(text: str) -> bool:
    """Heuristically detect whether a response is likely written in English."""
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
    """Return deterministic German fallback text based on the inferred tool call."""
    if tool_call is None:
        return "Bitte formuliere die Anfrage auf Deutsch und etwas genauer."

    name = tool_call["name"]
    if name == TOOL_START_TIMER:
        duration = tool_call["arguments"].get("duration", str(DEFAULT_TIMER_MINUTES))
        return f"Ich starte den Timer mit der Dauer {duration}."
    if name == TOOL_STOP_TIMER:
        return "Ich stoppe den laufenden Timer."
    if name == TOOL_PAUSE_TIMER:
        return "Ich pausiere den Timer."
    if name == TOOL_CONTINUE_TIMER:
        return "Ich setze den Timer fort."
    if name == TOOL_RESET_TIMER:
        return "Ich setze den Timer zurueck."
    if name == TOOL_START_POMODORO:
        topic = tool_call["arguments"].get("focus_topic", DEFAULT_FOCUS_TOPIC_DE)
        return f"Ich starte eine Pomodoro Sitzung fuer {topic}."
    if name == TOOL_STOP_POMODORO:
        return "Ich stoppe die aktuelle Pomodoro Sitzung."
    if name == TOOL_PAUSE_POMODORO:
        return "Ich pausiere die Pomodoro Sitzung."
    if name == TOOL_CONTINUE_POMODORO:
        return "Ich setze die Pomodoro Sitzung fort."
    if name == TOOL_RESET_POMODORO:
        return "Ich setze die Pomodoro Sitzung zurueck."
    if name == TOOL_SHOW_UPCOMING_EVENTS:
        return "Ich zeige die anstehenden Termine im gewuenschten Zeitraum."
    if name == TOOL_ADD_CALENDAR_EVENT:
        return "Ich lege den Kalendereintrag an."
    return "Anfrage verarbeitet."

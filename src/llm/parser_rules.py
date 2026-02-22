"""Intent-detection rules and legacy alias mappings for tool calls."""

from __future__ import annotations

import re
from typing import Optional

from pomodoro.constants import (
    ACTION_CONTINUE,
    ACTION_PAUSE,
    ACTION_RESET,
    ACTION_START,
)
from contracts.tool_contract import INTENT_STOP

# Backward-compat aliases emitted by older prompts.
LEGACY_TOOL_TIMER_START = "timer_start"
LEGACY_TOOL_TIMER_PAUSE = "timer_pause"
LEGACY_TOOL_TIMER_CONTINUE = "timer_continue"
LEGACY_TOOL_TIMER_ABORT = "timer_abort"
LEGACY_TOOL_TIMER_STOP = "timer_stop"
LEGACY_TOOL_TIMER_RESET = "timer_reset"

LEGACY_ACTION_BY_TOOL: dict[str, str] = {
    LEGACY_TOOL_TIMER_START: ACTION_START,
    LEGACY_TOOL_TIMER_PAUSE: ACTION_PAUSE,
    LEGACY_TOOL_TIMER_CONTINUE: ACTION_CONTINUE,
    LEGACY_TOOL_TIMER_ABORT: INTENT_STOP,
    LEGACY_TOOL_TIMER_STOP: INTENT_STOP,
    LEGACY_TOOL_TIMER_RESET: ACTION_RESET,
}

ACTION_PATTERNS: dict[str, re.Pattern[str]] = {
    ACTION_START: re.compile(r"\b(start|starte|beginn|beginne|anfang|los)\b", re.I),
    ACTION_PAUSE: re.compile(
        r"\b(pause|pausier|anhalten|stopp kurz|kurz stoppen)\b",
        re.I,
    ),
    ACTION_CONTINUE: re.compile(
        r"\b(weiter|fortsetzen|resume|fortfuehren|weiterlaufen)\b",
        re.I,
    ),
    INTENT_STOP: re.compile(r"\b(stop|stopp|beenden|abbrechen|abbruch|cancel)\b", re.I),
    ACTION_RESET: re.compile(r"\b(reset|zuruecksetzen|neu starten|von vorne)\b", re.I),
}


def detect_action(prompt: str) -> Optional[str]:
    """Detect the latest matching action keyword in the prompt text."""
    matches: list[tuple[int, str]] = []
    for action, pattern in ACTION_PATTERNS.items():
        for match in pattern.finditer(prompt):
            matches.append((match.start(), action))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[-1][1]


def has_pomodoro_context(text: str) -> bool:
    """Return whether text mentions pomodoro-like session context."""
    return bool(re.search(r"\b(pomodoro|fokus|fokussitzung|sitzung)\b", text))


def has_timer_context(text: str) -> bool:
    """Return whether text explicitly references timer context."""
    return bool(re.search(r"\b(timer|countdown)\b", text))


def looks_like_add_calendar(lowered_prompt: str) -> bool:
    """Heuristically detect calendar creation intent from prompt text."""
    has_calendar = bool(re.search(r"\b(kalender|termin|event)\b", lowered_prompt))
    has_create = bool(
        re.search(
            r"\b(hinzufuegen|hinzufueg|hinzufügen|fuege|füge|hinzu|anlegen|erstellen|eintragen|planen)\b",
            lowered_prompt,
        )
    )
    return has_calendar and has_create


def looks_like_show_events(lowered_prompt: str) -> bool:
    """Heuristically detect calendar listing intent from prompt text."""
    has_calendar = bool(re.search(r"\b(kalender|termin|termine|event|events)\b", lowered_prompt))
    has_show = bool(
        re.search(
            r"\b(zeigen|zeige|anzeigen|welche|anstehend|kommend|bevorstehend|was steht an)\b",
            lowered_prompt,
        )
    )
    return has_calendar and has_show

from __future__ import annotations

import re
from typing import Optional

# Backward-compat aliases emitted by older prompts.
LEGACY_ACTION_BY_TOOL: dict[str, str] = {
    "timer_start": "start",
    "timer_pause": "pause",
    "timer_continue": "continue",
    "timer_abort": "stop",
    "timer_stop": "stop",
    "timer_reset": "reset",
}

ACTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "start": re.compile(r"\b(start|starte|beginn|beginne|anfang|los)\b", re.I),
    "pause": re.compile(r"\b(pause|pausier|anhalten|stopp kurz|kurz stoppen)\b", re.I),
    "continue": re.compile(
        r"\b(weiter|fortsetzen|resume|fortfuehren|weiterlaufen)\b",
        re.I,
    ),
    "stop": re.compile(r"\b(stop|stopp|beenden|abbrechen|abbruch|cancel)\b", re.I),
    "reset": re.compile(r"\b(reset|zuruecksetzen|neu starten|von vorne)\b", re.I),
}


def detect_action(prompt: str) -> Optional[str]:
    matches: list[tuple[int, str]] = []
    for action, pattern in ACTION_PATTERNS.items():
        for match in pattern.finditer(prompt):
            matches.append((match.start(), action))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[-1][1]


def has_pomodoro_context(text: str) -> bool:
    return bool(re.search(r"\b(pomodoro|fokus|fokussitzung|sitzung)\b", text))


def has_timer_context(text: str) -> bool:
    return bool(re.search(r"\b(timer|countdown)\b", text))


def looks_like_add_calendar(lowered_prompt: str) -> bool:
    has_calendar = bool(re.search(r"\b(kalender|termin|event)\b", lowered_prompt))
    has_create = bool(
        re.search(
            r"\b(hinzufuegen|hinzufueg|hinzufügen|fuege|füge|hinzu|anlegen|erstellen|eintragen|planen)\b",
            lowered_prompt,
        )
    )
    return has_calendar and has_create


def looks_like_show_events(lowered_prompt: str) -> bool:
    has_calendar = bool(re.search(r"\b(kalender|termin|termine|event|events)\b", lowered_prompt))
    has_show = bool(
        re.search(
            r"\b(zeigen|zeige|anzeigen|welche|anstehend|kommend|bevorstehend|was steht an)\b",
            lowered_prompt,
        )
    )
    return has_calendar and has_show

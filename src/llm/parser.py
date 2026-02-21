from __future__ import annotations

import json
from datetime import datetime, timedelta
import re
from typing import Any, Optional, cast

from .types import StructuredResponse, ToolCall, ToolName

TOOL_NAMES: set[str] = {
    "start_timer",
    "stop_timer",
    "pause_timer",
    "continue_timer",
    "reset_timer",
    "start_pomodoro_session",
    "stop_pomodoro_session",
    "pause_pomodoro_session",
    "continue_pomodoro_session",
    "reset_pomodoro_session",
    "show_upcoming_events",
    "add_calendar_event",
}

ACTION_TO_TIMER_TOOL: dict[str, str] = {
    "start": "start_timer",
    "pause": "pause_timer",
    "continue": "continue_timer",
    "stop": "stop_timer",
    "reset": "reset_timer",
}

ACTION_TO_POMODORO_TOOL: dict[str, str] = {
    "start": "start_pomodoro_session",
    "pause": "pause_pomodoro_session",
    "continue": "continue_pomodoro_session",
    "stop": "stop_pomodoro_session",
    "reset": "reset_pomodoro_session",
}

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


class ResponseParser:
    def __init__(self):
        self._last_focus_topic: Optional[str] = None
        self._last_time_range: str = "heute"

    def parse(self, content: str, user_prompt: str) -> StructuredResponse:
        parsed = self._load_json_object(content)
        if parsed is not None:
            normalized = self._validate_and_normalize(parsed, user_prompt)
            if normalized is not None:
                return normalized

        inferred = self._infer_tool_call_from_prompt(user_prompt)
        return {
            "assistant_text": self._fallback_assistant_text(inferred),
            "tool_call": inferred,
        }

    def _load_json_object(self, content: str) -> Optional[dict[str, Any]]:
        text = content.strip()
        if not text:
            return None

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        snippet = text[start : end + 1]
        try:
            parsed = json.loads(snippet)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _validate_and_normalize(
        self, obj: dict[str, Any], user_prompt: str
    ) -> Optional[StructuredResponse]:
        assistant_raw = obj.get("assistant_text")
        if isinstance(assistant_raw, str):
            assistant_text = assistant_raw.strip()
        elif assistant_raw is None:
            assistant_text = ""
        else:
            assistant_text = str(assistant_raw).strip()

        tool_call = self._normalize_tool_call(obj.get("tool_call"), user_prompt)
        if tool_call is None:
            tool_call = self._infer_tool_call_from_prompt(user_prompt)

        assistant_text = self._normalize_assistant_text(assistant_text, tool_call)
        return {"assistant_text": assistant_text, "tool_call": tool_call}

    def _normalize_tool_call(
        self, tool_call: Any, user_prompt: str
    ) -> Optional[ToolCall]:
        if tool_call is None:
            return None
        if not isinstance(tool_call, dict):
            return None

        raw_name = tool_call.get("name")
        if not isinstance(raw_name, str):
            return None

        raw_arguments = tool_call.get("arguments")
        arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
        normalized_name = self._resolve_tool_name(raw_name, arguments, user_prompt)
        if normalized_name is None:
            return None

        normalized_arguments = self._normalize_arguments_for_tool(
            normalized_name, arguments, user_prompt
        )
        if normalized_arguments is None:
            return None

        return {
            "name": cast(ToolName, normalized_name),
            "arguments": normalized_arguments,
        }

    def _resolve_tool_name(
        self, raw_name: str, arguments: dict[str, Any], user_prompt: str
    ) -> Optional[str]:
        normalized_name = raw_name.strip()
        if normalized_name in TOOL_NAMES:
            return normalized_name

        action = LEGACY_ACTION_BY_TOOL.get(normalized_name)
        if action is None:
            return None

        if normalized_name == "timer_start":
            if "focus_topic" in arguments or "session" in arguments:
                return ACTION_TO_POMODORO_TOOL[action]
            if "duration" in arguments:
                return ACTION_TO_TIMER_TOOL[action]

        lowered = user_prompt.lower()
        has_pomodoro_context = self._has_pomodoro_context(lowered)
        has_timer_context = self._has_timer_context(lowered)

        if has_pomodoro_context and not has_timer_context:
            return ACTION_TO_POMODORO_TOOL[action]
        if has_timer_context and not has_pomodoro_context:
            return ACTION_TO_TIMER_TOOL[action]

        # Keep legacy behavior as default for ambiguous old aliases.
        return ACTION_TO_POMODORO_TOOL[action]

    def _normalize_arguments_for_tool(
        self, tool_name: str, arguments: dict[str, Any], user_prompt: str
    ) -> Optional[dict[str, Any]]:
        if tool_name == "start_timer":
            duration = self._normalize_duration(arguments.get("duration"))
            if duration is None:
                duration = self._extract_duration_from_prompt(user_prompt) or "10"
            return {"duration": duration}

        if tool_name in {
            "stop_timer",
            "pause_timer",
            "continue_timer",
            "reset_timer",
            "stop_pomodoro_session",
            "pause_pomodoro_session",
            "continue_pomodoro_session",
            "reset_pomodoro_session",
        }:
            return {}

        if tool_name == "start_pomodoro_session":
            raw_topic = (
                arguments.get("focus_topic")
                or arguments.get("session")
                or self._extract_focus_topic(user_prompt)
                or self._last_focus_topic
                or "Fokus"
            )
            topic = self._sanitize_text(raw_topic, max_len=60) or "Fokus"
            self._last_focus_topic = topic
            return {"focus_topic": topic}

        if tool_name == "show_upcoming_events":
            time_range = self._sanitize_time_range(
                arguments.get("time_range")
                or self._extract_time_range(user_prompt)
                or self._last_time_range
                or "heute"
            )
            self._last_time_range = time_range
            return {"time_range": time_range}

        if tool_name == "add_calendar_event":
            title = self._sanitize_text(
                arguments.get("title") or self._extract_calendar_title(user_prompt),
                max_len=120,
            )
            start_time = self._sanitize_text(
                arguments.get("start_time")
                or self._extract_datetime_literal(user_prompt),
                max_len=64,
            )
            end_time = self._sanitize_text(arguments.get("end_time"), max_len=64)
            duration = self._normalize_duration(arguments.get("duration"))

            if not title or not start_time:
                return None

            payload: dict[str, Any] = {
                "title": title,
                "start_time": start_time,
            }
            if end_time:
                payload["end_time"] = end_time
            elif duration:
                payload["duration"] = duration
            return payload

        return None

    def _infer_tool_call_from_prompt(self, user_prompt: str) -> Optional[ToolCall]:
        prompt = user_prompt.strip()
        lowered = prompt.lower()

        if self._looks_like_add_calendar(lowered):
            arguments = self._normalize_arguments_for_tool("add_calendar_event", {}, prompt)
            if arguments is not None:
                return {
                    "name": cast(ToolName, "add_calendar_event"),
                    "arguments": arguments,
                }
            return None

        if self._looks_like_show_events(lowered):
            arguments = self._normalize_arguments_for_tool(
                "show_upcoming_events", {}, prompt
            )
            if arguments is not None:
                return {
                    "name": cast(ToolName, "show_upcoming_events"),
                    "arguments": arguments,
                }
            return None

        action = self._detect_action(prompt)
        if action is None:
            return None

        has_pomodoro_context = self._has_pomodoro_context(lowered)
        has_timer_context = self._has_timer_context(lowered)
        duration = self._extract_duration_from_prompt(prompt)

        if has_pomodoro_context:
            name = ACTION_TO_POMODORO_TOOL[action]
            arguments = self._normalize_arguments_for_tool(name, {}, prompt)
            if arguments is None:
                return None
            return {
                "name": cast(ToolName, name),
                "arguments": arguments,
            }

        if has_timer_context or duration is not None:
            name = ACTION_TO_TIMER_TOOL[action]
            seed_args = {"duration": duration} if duration and name == "start_timer" else {}
            arguments = self._normalize_arguments_for_tool(name, seed_args, prompt)
            if arguments is None:
                return None
            return {
                "name": cast(ToolName, name),
                "arguments": arguments,
            }

        return None

    @staticmethod
    def _detect_action(prompt: str) -> Optional[str]:
        matches: list[tuple[int, str]] = []
        for action, pattern in ACTION_PATTERNS.items():
            for match in pattern.finditer(prompt):
                matches.append((match.start(), action))
        if not matches:
            return None
        matches.sort(key=lambda item: item[0])
        return matches[-1][1]

    @staticmethod
    def _has_pomodoro_context(text: str) -> bool:
        return bool(re.search(r"\b(pomodoro|fokus|fokussitzung|sitzung)\b", text))

    @staticmethod
    def _has_timer_context(text: str) -> bool:
        return bool(re.search(r"\b(timer|countdown)\b", text))

    @staticmethod
    def _sanitize_text(value: Any, *, max_len: int) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        text = re.sub(r"\s+", " ", text)
        return text[:max_len].strip()

    def _normalize_duration(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            minutes = int(value)
            return str(minutes) if minutes > 0 else None
        if not isinstance(value, str):
            return None

        raw = value.strip().lower()
        if not raw:
            return None

        plain = re.fullmatch(r"\d{1,4}", raw)
        if plain:
            return plain.group(0)

        match = re.search(
            r"(\d{1,4})\s*(sek|sekunde|sekunden|s|min|minute|minuten|m|stunde|stunden|h)",
            raw,
        )
        if not match:
            return None

        amount = int(match.group(1))
        unit = match.group(2)
        if amount <= 0:
            return None
        if unit in {"sek", "sekunde", "sekunden", "s"}:
            return f"{amount}s"
        if unit in {"stunde", "stunden", "h"}:
            return f"{amount}h"
        return f"{amount}m"

    def _extract_duration_from_prompt(self, prompt: str) -> Optional[str]:
        return self._normalize_duration(prompt)

    @staticmethod
    def _extract_focus_topic(prompt: str) -> Optional[str]:
        quoted = re.search(r"[\"'“”„](.+?)[\"'“”„]", prompt)
        if quoted:
            return quoted.group(1)

        match = re.search(
            r"\b(?:fuer|für|zu|zum|am)\s+([a-zA-Z0-9äöüÄÖÜß][\wäöüÄÖÜß\-\s]{1,60})",
            prompt,
            re.I,
        )
        if not match:
            return None

        topic = match.group(1)
        topic = re.split(r"\b(?:in|um|ab|morgen|heute)\b", topic, flags=re.I)[0]
        return topic.strip() or None

    def _sanitize_time_range(self, value: Any) -> str:
        text = self._sanitize_text(value, max_len=64).lower()
        if not text:
            return "heute"
        text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        return text

    def _extract_time_range(self, prompt: str) -> Optional[str]:
        lowered = prompt.lower()
        if "uebermorgen" in lowered or "übermorgen" in lowered:
            return "uebermorgen"
        if "morgen" in lowered:
            return "morgen"
        if "naechste woche" in lowered or "nächste woche" in lowered:
            return "naechste woche"
        days_match = re.search(
            r"(naechste|nächste)\s+(\d+)\s+tage",
            lowered,
        )
        if days_match:
            return f"naechste {days_match.group(2)} tage"
        if "heute" in lowered:
            return "heute"
        return None

    @staticmethod
    def _extract_calendar_title(prompt: str) -> Optional[str]:
        quoted = re.search(r"(?:titel|title)?\s*[\"'“”„](.+?)[\"'“”„]", prompt, re.I)
        if quoted:
            return quoted.group(1)

        titled = re.search(r"\b(?:titel|title)\s+([a-zA-Z0-9äöüÄÖÜß][\wäöüÄÖÜß\-\s]{2,120})", prompt, re.I)
        if titled:
            candidate = re.split(
                r"\b(?:am|um|ab|von|fuer|für|dauer|start|ende|hinzu)\b",
                titled.group(1),
                flags=re.I,
            )[0]
            return candidate.strip() or None

        match = re.search(
            r"\b(?:termin|event)\s+(?:mit\s+dem\s+titel\s+)?([a-zA-Z0-9äöüÄÖÜß][\wäöüÄÖÜß\-\s]{2,120})",
            prompt,
            re.I,
        )
        if not match:
            return None
        candidate = re.split(
            r"\b(?:am|um|ab|von|fuer|für|dauer|start|ende|hinzu)\b",
            match.group(1),
            flags=re.I,
        )[0]
        return candidate.strip() or None

    @staticmethod
    def _extract_datetime_literal(prompt: str) -> Optional[str]:
        iso_match = re.search(
            r"\b(\d{4}-\d{2}-\d{2}[T\s]\d{1,2}:\d{2}(?::\d{2})?)\b",
            prompt,
        )
        if iso_match:
            return iso_match.group(1).replace(" ", "T")

        de_match = re.search(
            r"\b(\d{1,2}\.\d{1,2}\.\d{4})\s*(?:um|,)?\s*(\d{1,2}:\d{2})\b",
            prompt,
            re.I,
        )
        if de_match:
            date_part, time_part = de_match.groups()
            day, month, year = date_part.split(".")
            return f"{year}-{int(month):02d}-{int(day):02d}T{time_part}"

        relative_match = re.search(
            r"\b(heute|morgen|uebermorgen|übermorgen)\s*(?:um\s*)?(\d{1,2})(?::(\d{2}))?\s*uhr?\b",
            prompt,
            re.I,
        )
        if relative_match:
            day_token, hour_raw, minute_raw = relative_match.groups()
            day_key = day_token.lower()
            offset_days = {"heute": 0, "morgen": 1, "uebermorgen": 2, "übermorgen": 2}
            hour = int(hour_raw)
            minute = int(minute_raw or "0")
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                target = (datetime.now().astimezone() + timedelta(days=offset_days[day_key])).replace(
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0,
                )
                return target.isoformat(timespec="minutes")
        return None

    @staticmethod
    def _looks_like_add_calendar(lowered_prompt: str) -> bool:
        has_calendar = bool(re.search(r"\b(kalender|termin|event)\b", lowered_prompt))
        has_create = bool(
            re.search(
                r"\b(hinzufuegen|hinzufueg|hinzufügen|fuege|füge|hinzu|anlegen|erstellen|eintragen|planen)\b",
                lowered_prompt,
            )
        )
        return has_calendar and has_create

    @staticmethod
    def _looks_like_show_events(lowered_prompt: str) -> bool:
        has_calendar = bool(re.search(r"\b(kalender|termin|termine|event|events)\b", lowered_prompt))
        has_show = bool(
            re.search(
                r"\b(zeigen|zeige|anzeigen|welche|anstehend|kommend|bevorstehend|was steht an)\b",
                lowered_prompt,
            )
        )
        return has_calendar and has_show

    def _normalize_assistant_text(
        self, text: str, tool_call: Optional[ToolCall]
    ) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return self._fallback_assistant_text(tool_call)
        if normalized.lower() in {"ok", "okay", "klar", "verstanden"} and tool_call is not None:
            return self._fallback_assistant_text(tool_call)
        if self._is_probably_english(normalized):
            return self._fallback_assistant_text(tool_call)
        return normalized

    @staticmethod
    def _is_probably_english(text: str) -> bool:
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

    def _fallback_assistant_text(self, tool_call: Optional[ToolCall]) -> str:
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

from __future__ import annotations

import json
import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, TypedDict


ToolName = Literal[
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
]


class ToolCall(TypedDict):
    name: ToolName
    arguments: Dict[str, Any]


class StructuredResponse(TypedDict):
    assistant_text: str
    tool_call: Optional[ToolCall]


@dataclass(frozen=True)
class EnvironmentContext:
    """Read-only factual context passed to the model."""

    now_local: str
    light_level_lux: Optional[float] = None
    air_quality: Optional[Dict[str, Any]] = None
    upcoming_events: Optional[list[Dict[str, Any]]] = None

    def to_prompt_placeholders(self) -> Dict[str, str]:
        return {
            "current_time": self._format_current_time(),
            "current_date": self._format_current_date(),
            "next_appointment": self._format_next_appointment(),
            "air_quality": self._format_air_quality(),
            "ambient_light": self._format_ambient_light(),
        }

    def _format_current_time(self) -> str:
        now = self._parse_now_local()
        if now is None:
            return "Unbekannte Zeit"
        return now.strftime("%H:%M")

    def _format_current_date(self) -> str:
        now = self._parse_now_local()
        if now is None:
            return "Unbekanntes Datum"

        weekdays = (
            "Montag",
            "Dienstag",
            "Mittwoch",
            "Donnerstag",
            "Freitag",
            "Samstag",
            "Sonntag",
        )
        months = (
            "Januar",
            "Februar",
            "Maerz",
            "April",
            "Mai",
            "Juni",
            "Juli",
            "August",
            "September",
            "Oktober",
            "November",
            "Dezember",
        )
        weekday = weekdays[now.weekday()]
        month = months[now.month - 1]
        return f"{weekday}, {now.day}. {month} {now.year}"

    def _format_next_appointment(self) -> str:
        events = self.upcoming_events or []
        if not events:
            return "Kein anstehender Termin"

        first_event = events[0] if isinstance(events[0], dict) else {}
        summary = str(first_event.get("summary") or "Termin ohne Titel").strip()
        start = str(first_event.get("start") or "").strip()
        if start:
            return f"{summary} um {start}"
        return summary

    def _format_air_quality(self) -> str:
        payload = self.air_quality
        if payload is None:
            return "Keine Daten"
        if not isinstance(payload, dict):
            return str(payload)

        parts: list[str] = []
        aqi = payload.get("aqi")
        if aqi is not None:
            parts.append(f"AQI {aqi}")
        tvoc = payload.get("tvoc_ppb")
        if tvoc is not None:
            parts.append(f"TVOC {tvoc} ppb")
        eco2 = payload.get("eco2_ppm")
        if eco2 is not None:
            parts.append(f"eCO2 {eco2} ppm")
        if parts:
            return ", ".join(parts)

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _format_ambient_light(self) -> str:
        if self.light_level_lux is None:
            return "Keine Daten"

        value = float(self.light_level_lux)
        if value.is_integer():
            return f"{int(value)} lux"
        return f"{value:.2f}".rstrip("0").rstrip(".") + " lux"

    def _parse_now_local(self) -> Optional[dt.datetime]:
        value = self.now_local.strip()
        if not value:
            return None

        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            return dt.datetime.fromisoformat(normalized)
        except ValueError:
            return None

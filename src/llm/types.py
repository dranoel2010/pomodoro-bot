"""Typed payloads shared across LLM backend, parser, and runtime integration."""

from __future__ import annotations

import json
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, TypedDict

from contracts.tool_contract import TOOL_NAME_ORDER

ToolName = Literal[*TOOL_NAME_ORDER]


class ToolCall(TypedDict):
    """Typed structure for a single normalized runtime tool invocation."""
    name: ToolName
    arguments: Dict[str, Any]


class StructuredResponse(TypedDict):
    """Typed schema produced by the parser and consumed by runtime."""
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
        start_raw = first_event.get("start")
        end_raw = first_event.get("end")
        event_text = self._format_event_window(start_raw, end_raw)
        if event_text:
            return f"{summary} ({event_text})"
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

    @staticmethod
    def _to_reference_timezone(
        value: dt.datetime,
        *,
        reference: dt.datetime,
    ) -> dt.datetime:
        target_tz = reference.tzinfo or dt.timezone.utc
        if value.tzinfo is None:
            return value.replace(tzinfo=target_tz)
        return value.astimezone(target_tz)

    @staticmethod
    def _relative_day_label(target: dt.date, reference: dt.date) -> str:
        if target == reference:
            return "heute"
        if target == (reference + dt.timedelta(days=1)):
            return "morgen"
        if target == (reference - dt.timedelta(days=1)):
            return "gestern"
        return f"am {target.day:02d}.{target.month:02d}.{target.year}"

    def _parse_event_datetime(self, value: Any) -> Optional[dt.datetime]:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw:
            return None

        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            parsed = dt.datetime.fromisoformat(normalized)
        except ValueError:
            return None

        reference = self._parse_now_local() or dt.datetime.now().astimezone()
        return self._to_reference_timezone(parsed, reference=reference)

    @staticmethod
    def _is_all_day_date_string(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()))

    def _format_event_point(self, value: Any) -> Optional[str]:
        parsed = self._parse_event_datetime(value)
        if parsed is None:
            return None

        reference = self._parse_now_local() or dt.datetime.now().astimezone()
        day_label = self._relative_day_label(parsed.date(), reference.date())
        if self._is_all_day_date_string(value):
            return f"{day_label}, ganztaegig"
        return f"{day_label} um {parsed.strftime('%H:%M')}"

    def _format_event_window(self, start_value: Any, end_value: Any) -> Optional[str]:
        start_point = self._format_event_point(start_value)
        if start_point is None:
            return None
        if self._is_all_day_date_string(start_value):
            return start_point

        start_dt = self._parse_event_datetime(start_value)
        end_dt = self._parse_event_datetime(end_value)
        if start_dt is None or end_dt is None:
            return start_point

        if start_dt.date() == end_dt.date():
            reference = self._parse_now_local() or dt.datetime.now().astimezone()
            day_label = self._relative_day_label(start_dt.date(), reference.date())
            return f"{day_label} von {start_dt.strftime('%H:%M')} bis {end_dt.strftime('%H:%M')}"

        end_point = self._format_event_point(end_value)
        if end_point is None:
            return start_point
        return f"von {start_point} bis {end_point}"

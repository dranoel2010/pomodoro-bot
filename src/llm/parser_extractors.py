from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable, Optional


def sanitize_text(value: Any, *, max_len: int) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_len].strip()


def _resolve_reference_now(now_fn: Optional[Callable[[], datetime]]) -> datetime:
    reference = now_fn() if now_fn is not None else datetime.now().astimezone()
    if reference.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        return reference.replace(tzinfo=local_tz)
    return reference


def _ensure_timezone(
    value: datetime,
    *,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> datetime:
    if value.tzinfo is not None:
        return value
    reference = _resolve_reference_now(now_fn)
    return value.replace(tzinfo=reference.tzinfo or timezone.utc)


def normalize_calendar_datetime_input(
    value: Any,
    *,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> Optional[str]:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    iso_candidate = raw.replace(" ", "T")
    if iso_candidate.endswith("Z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        parsed = _ensure_timezone(parsed, now_fn=now_fn)
        return parsed.isoformat(timespec="minutes")
    except ValueError:
        pass

    de_match = re.fullmatch(
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(?:um|,)?\s*(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?",
        raw,
        re.I,
    )
    if de_match:
        day, month, year, hour_raw, minute_raw = de_match.groups()
        hour = int(hour_raw)
        minute = int(minute_raw or "0")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        try:
            parsed = datetime(
                year=int(year),
                month=int(month),
                day=int(day),
                hour=hour,
                minute=minute,
            )
        except ValueError:
            return None
        parsed = _ensure_timezone(parsed, now_fn=now_fn)
        return parsed.isoformat(timespec="minutes")

    relative_match = re.fullmatch(
        r"(heute|morgen|uebermorgen|übermorgen)\s*(?:um\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?",
        raw,
        re.I,
    )
    if relative_match:
        day_token, hour_raw, minute_raw = relative_match.groups()
        hour = int(hour_raw)
        minute = int(minute_raw or "0")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        day_key = day_token.lower()
        offset_days = {"heute": 0, "morgen": 1, "uebermorgen": 2, "übermorgen": 2}
        base = _resolve_reference_now(now_fn)
        target = (base + timedelta(days=offset_days[day_key])).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        return target.isoformat(timespec="minutes")

    return None


def normalize_duration(value: Any) -> Optional[str]:
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


def extract_duration_from_prompt(prompt: str) -> Optional[str]:
    return normalize_duration(prompt)


def extract_focus_topic(prompt: str) -> Optional[str]:
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


def sanitize_time_range(value: Any) -> str:
    text = sanitize_text(value, max_len=64).lower()
    if not text:
        return "heute"
    return text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")


def extract_time_range(prompt: str) -> Optional[str]:
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


def extract_calendar_title(prompt: str) -> Optional[str]:
    quoted = re.search(r"(?:titel|title)?\s*[\"'“”„](.+?)[\"'“”„]", prompt, re.I)
    if quoted:
        return quoted.group(1)

    titled = re.search(
        r"\b(?:titel|title)\s+([a-zA-Z0-9äöüÄÖÜß][\wäöüÄÖÜß\-\s]{2,120})",
        prompt,
        re.I,
    )
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


def extract_datetime_literal(
    prompt: str,
    *,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> Optional[str]:
    iso_match = re.search(
        r"\b(\d{4}-\d{2}-\d{2}[T\s]\d{1,2}:\d{2}(?::\d{2})?)\b",
        prompt,
    )
    if iso_match:
        return normalize_calendar_datetime_input(
            iso_match.group(1),
            now_fn=now_fn,
        )

    de_match = re.search(
        r"\b(\d{1,2}\.\d{1,2}\.\d{4})\s*(?:um|,)?\s*(\d{1,2}[:.]\d{2})\b",
        prompt,
        re.I,
    )
    if de_match:
        date_part, time_part = de_match.groups()
        return normalize_calendar_datetime_input(
            f"{date_part} {time_part.replace('.', ':')}",
            now_fn=now_fn,
        )

    relative_match = re.search(
        r"\b(heute|morgen|uebermorgen|übermorgen)\s*(?:um\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*uhr?\b",
        prompt,
        re.I,
    )
    if relative_match:
        day_token, hour_raw, minute_raw = relative_match.groups()
        minute = minute_raw or "00"
        return normalize_calendar_datetime_input(
            f"{day_token} {hour_raw}:{minute}",
            now_fn=now_fn,
        )

    return None

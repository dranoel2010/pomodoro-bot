"""Shared parsing helpers for relative datetimes and duration values."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Callable


def resolve_reference_now(now_fn: Callable[[], datetime] | None = None) -> datetime:
    """Return a timezone-aware reference timestamp for relative parsing."""
    reference = now_fn() if now_fn is not None else datetime.now().astimezone()
    if reference.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        return reference.replace(tzinfo=local_tz)
    return reference


def parse_datetime_input(
    value: object,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> datetime | None:
    """Parse ISO, German absolute, or relative German datetime inputs."""
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
    except ValueError:
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
        else:
            relative_match = re.fullmatch(
                r"(heute|morgen|uebermorgen|übermorgen)\s*(?:um\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?",
                raw,
                re.I,
            )
            if not relative_match:
                return None
            day_token, hour_raw, minute_raw = relative_match.groups()
            hour = int(hour_raw)
            minute = int(minute_raw or "0")
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None
            day_key = day_token.lower()
            offset_days = {"heute": 0, "morgen": 1, "uebermorgen": 2, "übermorgen": 2}
            base = resolve_reference_now(now_fn)
            parsed = (base + timedelta(days=offset_days[day_key])).replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

    if parsed.tzinfo is not None:
        return parsed
    reference = resolve_reference_now(now_fn)
    return parsed.replace(tzinfo=reference.tzinfo or timezone.utc)


def normalize_datetime_input(
    value: object,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> str | None:
    """Parse a datetime-like value and return ISO-8601 (minutes precision)."""
    parsed = parse_datetime_input(value, now_fn=now_fn)
    if parsed is None:
        return None
    return parsed.isoformat(timespec="minutes")


def normalize_duration_token(value: object) -> str | None:
    """Normalize duration-like values into compact minute/second/hour tokens."""
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
        re.IGNORECASE,
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


def duration_seconds_from_value(value: object, *, default_seconds: int) -> int:
    """Parse duration input and return positive duration in seconds."""
    if isinstance(value, (int, float)) and int(value) > 0:
        return int(value) * 60
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw.isdigit():
            return max(1, int(raw)) * 60
        match = re.search(
            r"(\d{1,4})\s*(s|sek|sekunde|sekunden|m|min|minute|minuten|h|stunde|stunden)",
            raw,
        )
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            if unit in {"s", "sek", "sekunde", "sekunden"}:
                return max(1, amount)
            if unit in {"h", "stunde", "stunden"}:
                return max(1, amount) * 3600
            return max(1, amount) * 60
    return default_seconds

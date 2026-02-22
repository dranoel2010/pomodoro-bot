from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any, Optional

from spoken_time import format_spoken_clock

from .contracts import AppConfigLike, CalendarOracleLike


def parse_duration_seconds(value: Any, *, default_seconds: int) -> int:
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


def parse_calendar_datetime(value: Any) -> Optional[dt.datetime]:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    iso_candidate = raw.replace(" ", "T")
    if iso_candidate.endswith("Z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(iso_candidate)
    except ValueError:
        de_match = re.match(
            r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(?:um|,)?\s*(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?$",
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
                parsed = dt.datetime(
                    year=int(year),
                    month=int(month),
                    day=int(day),
                    hour=hour,
                    minute=minute,
                )
            except ValueError:
                return None
        else:
            relative_match = re.match(
                r"^(heute|morgen|uebermorgen|übermorgen)\s*(?:um\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr)?$",
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
            now = dt.datetime.now().astimezone()
            parsed = (now + dt.timedelta(days=offset_days[day_key])).replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

    if parsed.tzinfo is None:
        local_tz = dt.datetime.now().astimezone().tzinfo or dt.timezone.utc
        return parsed.replace(tzinfo=local_tz)
    return parsed


def _to_reference_timezone(
    value: dt.datetime,
    *,
    reference: dt.datetime,
) -> dt.datetime:
    target_tz = reference.tzinfo or dt.timezone.utc
    if value.tzinfo is None:
        return value.replace(tzinfo=target_tz)
    return value.astimezone(target_tz)


def _relative_day_label(target: dt.date, reference: dt.date) -> str:
    if target == reference:
        return "heute"
    if target == (reference + dt.timedelta(days=1)):
        return "morgen"
    if target == (reference - dt.timedelta(days=1)):
        return "gestern"
    return f"am {target.day:02d}.{target.month:02d}.{target.year}"


def format_calendar_datetime_natural(
    value: dt.datetime,
    *,
    now: Optional[dt.datetime] = None,
) -> str:
    reference = now or dt.datetime.now().astimezone()
    localized = _to_reference_timezone(value, reference=reference)
    day_label = _relative_day_label(localized.date(), reference.date())
    return f"{day_label} um {format_spoken_clock(localized)}"


def format_calendar_value_natural(
    value: Any,
    *,
    now: Optional[dt.datetime] = None,
) -> Optional[str]:
    raw = value.strip() if isinstance(value, str) else ""
    reference = now or dt.datetime.now().astimezone()

    is_all_day = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw))
    parsed = parse_calendar_datetime(value)
    if parsed is None:
        return None

    localized = _to_reference_timezone(parsed, reference=reference)
    day_label = _relative_day_label(localized.date(), reference.date())
    if is_all_day:
        return f"{day_label}, ganztaegig"
    return f"{day_label} um {format_spoken_clock(localized)}"


def format_calendar_window_natural(
    start: dt.datetime,
    end: dt.datetime,
    *,
    now: Optional[dt.datetime] = None,
) -> str:
    reference = now or dt.datetime.now().astimezone()
    start_local = _to_reference_timezone(start, reference=reference)
    end_local = _to_reference_timezone(end, reference=reference)
    if start_local.date() == end_local.date():
        day_label = _relative_day_label(start_local.date(), reference.date())
        return (
            f"{day_label} von {format_spoken_clock(start_local)} "
            f"bis {format_spoken_clock(end_local)}"
        )
    return (
        f"von {format_calendar_datetime_natural(start_local, now=reference)} "
        f"bis {format_calendar_datetime_natural(end_local, now=reference)}"
    )


def calendar_window_end(time_range: str) -> dt.datetime:
    now = dt.datetime.now().astimezone()
    lowered = time_range.lower()
    if "uebermorgen" in lowered:
        target = now + dt.timedelta(days=2)
        return target.replace(hour=23, minute=59, second=59, microsecond=0)
    if "morgen" in lowered:
        target = now + dt.timedelta(days=1)
        return target.replace(hour=23, minute=59, second=59, microsecond=0)
    if "naechste woche" in lowered:
        return now + dt.timedelta(days=7)
    days_match = re.search(r"naechste\s+(\d+)\s+tage", lowered)
    if days_match:
        return now + dt.timedelta(days=max(1, int(days_match.group(1))))
    if "heute" in lowered:
        return now.replace(hour=23, minute=59, second=59, microsecond=0)
    return now + dt.timedelta(days=3)


def handle_calendar_tool_call(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    oracle_service: Optional[CalendarOracleLike],
    app_config: AppConfigLike,
    logger: logging.Logger,
) -> str:
    if oracle_service is None:
        return "Kalenderfunktion ist derzeit nicht verfuegbar."

    try:
        if tool_name == "show_upcoming_events":
            time_range = str(arguments.get("time_range", "heute")).strip() or "heute"
            now = dt.datetime.now().astimezone()
            window_end = calendar_window_end(time_range)
            events = oracle_service.list_upcoming_events(
                max_results=app_config.oracle.google_calendar_max_results * 2,
                time_min=now,
            )

            filtered: list[dict[str, Any]] = []
            for event in events:
                start_raw = event.get("start")
                if not isinstance(start_raw, str):
                    continue
                parsed_start = parse_calendar_datetime(start_raw)
                if parsed_start is None:
                    continue
                if parsed_start <= window_end:
                    filtered.append(event)

            if not filtered:
                return f"Es gibt keine anstehenden Termine fuer {time_range}."

            top = filtered[: app_config.oracle.google_calendar_max_results]
            parts = []
            for item in top:
                summary = str(item.get("summary") or "Ohne Titel")
                start_text = format_calendar_value_natural(item.get("start"), now=now)
                if start_text is None:
                    start_text = str(item.get("start") or "ohne Zeit")
                parts.append(f"{summary} ({start_text})")
            return "Anstehende Termine: " + "; ".join(parts) + "."

        if tool_name == "add_calendar_event":
            title = str(arguments.get("title", "")).strip()
            start_time = parse_calendar_datetime(arguments.get("start_time"))
            end_time = parse_calendar_datetime(arguments.get("end_time"))
            duration_seconds = parse_duration_seconds(
                arguments.get("duration"),
                default_seconds=30 * 60,
            )
            if start_time is None:
                return "Ich konnte den Termin nicht anlegen, weil die Startzeit fehlt oder ungueltig ist."
            if not title:
                return "Ich konnte den Termin nicht anlegen, weil der Titel fehlt."
            if end_time is None:
                end_time = start_time + dt.timedelta(seconds=duration_seconds)
            if end_time <= start_time:
                end_time = start_time + dt.timedelta(seconds=duration_seconds)

            event_id = oracle_service.add_event(
                title=title,
                start=start_time,
                end=end_time,
            )
            logger.info(
                "Kalendereintrag erstellt (id=%s, title=%s, start=%s, end=%s)",
                event_id,
                title,
                start_time.isoformat(timespec="minutes"),
                end_time.isoformat(timespec="minutes"),
            )
            window_text = format_calendar_window_natural(
                start_time,
                end_time,
                now=dt.datetime.now().astimezone(),
            )
            return (
                f"Termin angelegt: {title}. Zeit: {window_text}."
            )
    except Exception as error:
        logger.error("Kalenderaktion fehlgeschlagen (%s): %s", tool_name, error)
        return f"Kalenderaktion fehlgeschlagen: {error}"

    return "Kalenderaktion verarbeitet."

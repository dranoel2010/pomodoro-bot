"""Shared helpers for training-dataset generation and validation."""

from __future__ import annotations

import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

_SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from contracts.tool_contract import (  # noqa: E402
    TOOL_ADD_CALENDAR_EVENT,
    TOOL_CONTINUE_POMODORO,
    TOOL_CONTINUE_TIMER,
    TOOL_NAMES,
    TOOL_PAUSE_POMODORO,
    TOOL_PAUSE_TIMER,
    TOOL_RESET_POMODORO,
    TOOL_RESET_TIMER,
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_START_POMODORO,
    TOOL_START_TIMER,
    TOOL_STOP_POMODORO,
    TOOL_STOP_TIMER,
    TOOLS_WITHOUT_ARGUMENTS,
)
from llm.parser import ResponseParser  # noqa: E402

Record = dict[str, Any]
Target = dict[str, Any]
ToolCall = dict[str, Any]

TARGET_DATASET_SIZE = 60_000
DEFAULT_SPLIT_SIZES: dict[str, int] = {"train": 48_000, "val": 6_000, "test": 6_000}
VALID_SPLITS = frozenset(DEFAULT_SPLIT_SIZES)
VALID_SOURCES = frozenset({"template", "teacher", "mutation", "hard_negative"})

TOOL_INTENTS: tuple[str, ...] = (
    TOOL_START_TIMER,
    TOOL_PAUSE_TIMER,
    TOOL_CONTINUE_TIMER,
    TOOL_STOP_TIMER,
    TOOL_RESET_TIMER,
    TOOL_START_POMODORO,
    TOOL_PAUSE_POMODORO,
    TOOL_CONTINUE_POMODORO,
    TOOL_STOP_POMODORO,
    TOOL_RESET_POMODORO,
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_ADD_CALENDAR_EVENT,
)

NULL_INTENTS: tuple[str, ...] = (
    "null_identity",
    "null_gratitude",
    "null_smalltalk",
    "null_prompt_injection",
    "null_ambiguous",
    "null_calendar_missing_slot",
    "null_timer_status_question",
    "null_definition_pomodoro",
)

PRIORITY_TOOL_INTENTS: frozenset[str] = frozenset(
    {
        TOOL_PAUSE_TIMER,
        TOOL_STOP_TIMER,
        TOOL_RESET_TIMER,
        TOOL_PAUSE_POMODORO,
        TOOL_STOP_POMODORO,
        TOOL_RESET_POMODORO,
        TOOL_SHOW_UPCOMING_EVENTS,
    }
)

FAILURE_PRONE_INTENTS: frozenset[str] = frozenset(
    {
        TOOL_PAUSE_TIMER,
        TOOL_STOP_TIMER,
        TOOL_RESET_TIMER,
        TOOL_PAUSE_POMODORO,
        TOOL_STOP_POMODORO,
        TOOL_RESET_POMODORO,
        TOOL_SHOW_UPCOMING_EVENTS,
        "null_prompt_injection",
        "null_ambiguous",
        "null_calendar_missing_slot",
    }
)

TOOL_REQUIRED_ARGUMENT_KEYS: dict[str, tuple[str, ...]] = {
    TOOL_START_TIMER: ("duration",),
    TOOL_START_POMODORO: ("focus_topic",),
    TOOL_SHOW_UPCOMING_EVENTS: ("time_range",),
    TOOL_ADD_CALENDAR_EVENT: ("title", "start_time"),
}

NULL_ASSISTANT_TEXT: dict[str, str] = {
    "null_identity": "Ich bin dein Fokus-Assistent fuer Timer, Pomodoro und Kalender.",
    "null_gratitude": "Gern.",
    "null_smalltalk": "Ich kann dir bei Fokusarbeit und Terminen helfen.",
    "null_prompt_injection": "Ich bleibe bei meinen Sicherheitsregeln.",
    "null_ambiguous": "Bitte sag mir kurz, welche Aktion ich ausfuehren soll.",
    "null_calendar_missing_slot": "Welche Startzeit soll der Termin haben?",
    "null_timer_status_question": "Ich kann den Timerstatus fuer dich pruefen, wenn du es willst.",
    "null_definition_pomodoro": "Ein Pomodoro ist ein Fokusintervall mit anschliessender Pause.",
}

GERMAN_UMLAUT_ASCII_MAP = {
    "ä": "ae",
    "ö": "oe",
    "ü": "ue",
    "Ä": "Ae",
    "Ö": "Oe",
    "Ü": "Ue",
    "ß": "ss",
}

ISO_WITH_TZ_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?[+-]\d{2}:\d{2}$")


@dataclass(frozen=True, slots=True)
class ValidationSummary:
    total_in: int
    total_out: int
    schema_rejected: int
    contract_rejected: int
    duplicate_rejected: int
    critic_disagreements: int


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def load_jsonl(path: Path) -> list[Record]:
    rows: list[Record] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no} in {path}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_no} in {path} is not a JSON object")
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: Iterable[Record]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(stable_json_dumps(row))
            handle.write("\n")
            count += 1
    return count


def replace_umlauts_ascii(text: str) -> str:
    out = text
    for key, value in GERMAN_UMLAUT_ASCII_MAP.items():
        out = out.replace(key, value)
    return out


def normalize_for_dedup(text: str) -> str:
    lowered = replace_umlauts_ascii(text).lower().strip()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _canonical_tool_call(tool_call: Any) -> ToolCall | None:
    if tool_call is None:
        return None
    if not isinstance(tool_call, dict):
        return None
    name = tool_call.get("name")
    arguments = tool_call.get("arguments")
    if not isinstance(name, str):
        return None
    if not isinstance(arguments, dict):
        return None
    return {"name": name, "arguments": dict(arguments)}


def canonicalize_target(*, user_text: str, target: Target) -> Target:
    parser = ResponseParser()
    content = stable_json_dumps(target)
    normalized = parser.parse(content, user_text)
    return {
        "assistant_text": str(normalized.get("assistant_text") or "").strip(),
        "tool_call": _canonical_tool_call(normalized.get("tool_call")),
    }


def deterministic_assistant_text(*, intent_class: str, tool_call: ToolCall | None) -> str:
    if tool_call is not None:
        parser = ResponseParser()
        return parser.fallback_assistant_text(tool_call)
    return NULL_ASSISTANT_TEXT.get(
        intent_class,
        "Bitte sag mir kurz, welche Aktion ich ausfuehren soll.",
    )


def infer_critic_target(*, user_text: str, intent_class: str) -> Target:
    parser = ResponseParser()
    tool_call = parser.infer_tool_call_from_prompt(user_text)
    return {
        "assistant_text": deterministic_assistant_text(intent_class=intent_class, tool_call=tool_call),
        "tool_call": tool_call,
    }


def is_iso_with_timezone(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if ISO_WITH_TZ_RE.fullmatch(value.strip()) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return False
    return parsed.tzinfo is not None


def tool_call_signature(tool_call: Any) -> str:
    normalized = _canonical_tool_call(tool_call)
    if normalized is None:
        return "null"
    return stable_json_dumps(normalized)


def target_signature(target: Any) -> str:
    if not isinstance(target, dict):
        return "invalid"
    return stable_json_dumps(
        {
            "assistant_text": str(target.get("assistant_text") or ""),
            "tool_call": _canonical_tool_call(target.get("tool_call")),
        }
    )


def validate_record_shape(record: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["record is not an object"]

    required_top_keys = {
        "id",
        "split",
        "user_text",
        "target",
        "intent_class",
        "noise_tags",
        "source",
        "quality",
        "provenance",
    }
    missing = sorted(required_top_keys.difference(record.keys()))
    if missing:
        errors.append(f"missing keys: {missing}")

    rec_id = record.get("id")
    if not isinstance(rec_id, str) or not rec_id.strip():
        errors.append("id must be non-empty string")

    split = record.get("split")
    if not isinstance(split, str) or split not in VALID_SPLITS:
        errors.append(f"split must be one of {sorted(VALID_SPLITS)!r}")

    user_text = record.get("user_text")
    if not isinstance(user_text, str) or not user_text.strip():
        errors.append("user_text must be non-empty string")

    intent_class = record.get("intent_class")
    if not isinstance(intent_class, str) or not intent_class.strip():
        errors.append("intent_class must be non-empty string")

    noise_tags = record.get("noise_tags")
    if not isinstance(noise_tags, list) or any(not isinstance(item, str) for item in noise_tags):
        errors.append("noise_tags must be list[str]")

    source = record.get("source")
    if not isinstance(source, str) or source not in VALID_SOURCES:
        errors.append(f"source must be one of {sorted(VALID_SOURCES)!r}")

    quality = record.get("quality")
    quality_keys = {"validator_pass", "critic_pass", "human_reviewed", "human_label_ok"}
    if not isinstance(quality, dict):
        errors.append("quality must be an object")
    else:
        missing_quality = sorted(quality_keys.difference(quality.keys()))
        if missing_quality:
            errors.append(f"quality missing keys: {missing_quality}")
        for key in quality_keys:
            if key in quality and not isinstance(quality.get(key), bool):
                errors.append(f"quality.{key} must be boolean")

    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("provenance must be an object")
    else:
        for key in ("template_id", "generator_model", "created_at"):
            value = provenance.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"provenance.{key} must be non-empty string")

    target = record.get("target")
    if not isinstance(target, dict):
        errors.append("target must be an object")
    else:
        assistant_text = target.get("assistant_text")
        if not isinstance(assistant_text, str) or not assistant_text.strip():
            errors.append("target.assistant_text must be non-empty string")

        tool_call = target.get("tool_call")
        if tool_call is not None:
            if not isinstance(tool_call, dict):
                errors.append("target.tool_call must be null or object")
            else:
                name = tool_call.get("name")
                arguments = tool_call.get("arguments")
                if not isinstance(name, str) or not name.strip():
                    errors.append("target.tool_call.name must be non-empty string")
                if not isinstance(arguments, dict):
                    errors.append("target.tool_call.arguments must be object")

    return errors


def validate_record_contract(record: Record) -> list[str]:
    errors: list[str] = []
    target = record.get("target")
    if not isinstance(target, dict):
        return ["target missing or invalid"]

    tool_call = target.get("tool_call")
    if tool_call is None:
        return errors
    if not isinstance(tool_call, dict):
        return ["target.tool_call must be object"]

    name = tool_call.get("name")
    arguments = tool_call.get("arguments")
    if not isinstance(name, str) or name not in TOOL_NAMES:
        errors.append(f"tool name not canonical: {name!r}")
        return errors
    if not isinstance(arguments, dict):
        errors.append("tool_call.arguments must be object")
        return errors

    required = TOOL_REQUIRED_ARGUMENT_KEYS.get(name, ())
    for key in required:
        value = arguments.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"required argument missing/invalid: {key}")

    if name in TOOLS_WITHOUT_ARGUMENTS and arguments:
        errors.append(f"{name} must use empty arguments")

    if name == TOOL_ADD_CALENDAR_EVENT:
        start_time = arguments.get("start_time")
        end_time = arguments.get("end_time")
        if not is_iso_with_timezone(start_time):
            errors.append("add_calendar_event.start_time must be ISO-8601 with timezone")
        if end_time is not None and not is_iso_with_timezone(end_time):
            errors.append("add_calendar_event.end_time must be ISO-8601 with timezone")

    return errors


def targets_match(lhs: Target, rhs: Target) -> bool:
    return tool_call_signature(lhs.get("tool_call")) == tool_call_signature(rhs.get("tool_call"))


def deep_copy_record(record: Record) -> Record:
    return json.loads(stable_json_dumps(record))


def allocate_counts(weights: dict[str, float], total: int) -> dict[str, int]:
    if total < 0:
        raise ValueError("total must be non-negative")
    if not weights:
        raise ValueError("weights must not be empty")
    if any(value <= 0 for value in weights.values()):
        raise ValueError("all weights must be > 0")

    raw = {key: (total * value / sum(weights.values())) for key, value in weights.items()}
    counts = {key: int(math.floor(value)) for key, value in raw.items()}
    remainder = total - sum(counts.values())
    if remainder > 0:
        ranked = sorted(raw, key=lambda key: (raw[key] - counts[key]), reverse=True)
        for idx in range(remainder):
            counts[ranked[idx % len(ranked)]] += 1
    return counts


def intent_distribution(records: Iterable[Record]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        intent = record.get("intent_class")
        if isinstance(intent, str):
            counter[intent] += 1
    return counter


def split_distribution(records: Iterable[Record]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        split = record.get("split")
        if isinstance(split, str):
            counter[split] += 1
    return counter


class NearDuplicateIndex:
    """Approximate near-duplicate index for large prompt datasets."""

    def __init__(self, *, ratio_threshold: float = 0.94, max_bucket_scan: int = 64):
        self._ratio_threshold = ratio_threshold
        self._max_bucket_scan = max_bucket_scan
        self._seen_exact: set[tuple[str, str, str]] = set()
        self._buckets: dict[tuple[str, str, int, str], list[str]] = defaultdict(list)

    def _bucket_key(self, *, normalized_text: str, intent_class: str, target_sig: str) -> tuple[str, str, int, str]:
        length_bucket = len(normalized_text) // 12
        prefix = normalized_text[:3]
        return (intent_class, target_sig, length_bucket, prefix)

    def add_if_new(self, *, text: str, intent_class: str, target_sig: str) -> bool:
        normalized = normalize_for_dedup(text)
        if not normalized:
            return False

        exact_key = (normalized, intent_class, target_sig)
        if exact_key in self._seen_exact:
            return False

        bucket = self._bucket_key(
            normalized_text=normalized,
            intent_class=intent_class,
            target_sig=target_sig,
        )
        candidates = self._buckets.get(bucket, [])
        for existing in candidates[-self._max_bucket_scan :]:
            ratio = SequenceMatcher(a=normalized, b=existing).ratio()
            if ratio >= self._ratio_threshold:
                return False

        self._seen_exact.add(exact_key)
        self._buckets[bucket].append(normalized)
        return True


def _group_by_intent(records: list[Record]) -> dict[str, list[Record]]:
    grouped: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        grouped[str(record["intent_class"])].append(record)
    return grouped


def stratified_split(
    records: list[Record],
    *,
    split_sizes: dict[str, int] | None = None,
    seed: int = 1337,
) -> dict[str, list[Record]]:
    if split_sizes is None:
        split_sizes = dict(DEFAULT_SPLIT_SIZES)

    total_requested = sum(split_sizes.values())
    if total_requested != len(records):
        raise ValueError(
            f"split size mismatch: requested {total_requested}, got {len(records)} records"
        )

    grouped = _group_by_intent(records)
    rng = random.Random(seed)
    for rows in grouped.values():
        rng.shuffle(rows)

    split_order = ["train", "val", "test"]
    target_ratio = {
        split: split_sizes[split] / total_requested
        for split in split_order
    }

    remaining = dict(split_sizes)
    assignments: dict[str, list[Record]] = {split: [] for split in split_order}

    intents = sorted(grouped.keys())
    for index, intent in enumerate(intents):
        rows = grouped[intent]
        n = len(rows)

        if index == len(intents) - 1:
            counts = dict(remaining)
        else:
            raw = {split: n * target_ratio[split] for split in split_order}
            counts = {split: int(math.floor(raw[split])) for split in split_order}
            deficit = n - sum(counts.values())
            ranked = sorted(split_order, key=lambda split: (raw[split] - counts[split]), reverse=True)
            for r_idx in range(deficit):
                counts[ranked[r_idx % len(ranked)]] += 1

            for split in split_order:
                if counts[split] > remaining[split]:
                    overflow = counts[split] - remaining[split]
                    counts[split] = remaining[split]
                    for receiver in split_order:
                        if receiver == split:
                            continue
                        capacity = remaining[receiver] - counts[receiver]
                        if capacity <= 0:
                            continue
                        delta = min(capacity, overflow)
                        counts[receiver] += delta
                        overflow -= delta
                        if overflow == 0:
                            break

        cursor = 0
        for split in split_order:
            take = counts[split]
            if take < 0:
                raise ValueError("invalid negative split count")
            if take > 0:
                chunk = rows[cursor : cursor + take]
                cursor += take
                assignments[split].extend(chunk)
            remaining[split] -= take

    if any(value != 0 for value in remaining.values()):
        raise ValueError(f"failed to assign exact split sizes: remaining={remaining}")

    for split in split_order:
        if len(assignments[split]) != split_sizes[split]:
            raise ValueError(
                f"split {split} size mismatch: expected {split_sizes[split]}, got {len(assignments[split])}"
            )

    for split in split_order:
        for record in assignments[split]:
            record["split"] = split

    return assignments


def tool_vs_null_ratio(records: Iterable[Record]) -> tuple[int, int]:
    tool_count = 0
    null_count = 0
    for record in records:
        target = record.get("target")
        tool_call = target.get("tool_call") if isinstance(target, dict) else None
        if tool_call is None:
            null_count += 1
        else:
            tool_count += 1
    return tool_count, null_count


def class_minimum_failures(records: Iterable[Record], *, minimum: int) -> dict[str, int]:
    counts = intent_distribution(records)
    return {intent: count for intent, count in counts.items() if count < minimum}

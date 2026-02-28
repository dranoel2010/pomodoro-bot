#!/usr/bin/env python3
"""Validate and filter raw candidate records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.common import (
    NULL_INTENTS,
    TOOL_INTENTS,
    NearDuplicateIndex,
    ValidationSummary,
    canonicalize_target,
    deep_copy_record,
    deterministic_assistant_text,
    infer_critic_target,
    stable_json_dumps,
    target_signature,
    targets_match,
    utc_now_iso,
    validate_record_contract,
    validate_record_shape,
    write_jsonl,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated dataset candidates")
    parser.add_argument("--in", dest="input_path", required=True)
    parser.add_argument("--out", dest="output_path", required=True)
    parser.add_argument(
        "--report-out",
        default="training/reports/validate_report_v1.json",
        help="Validation report JSON path",
    )
    parser.add_argument(
        "--dedup-threshold",
        type=float,
        default=0.985,
        help="Near-duplicate rejection threshold",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Line {line_no} is not an object")
            rows.append(payload)
    return rows


def _intent_target_alignment_error(record: dict) -> str | None:
    intent_class = record.get("intent_class")
    target = record.get("target")
    if not isinstance(intent_class, str) or not isinstance(target, dict):
        return "intent/target malformed"

    tool_call = target.get("tool_call")
    tool_name = tool_call.get("name") if isinstance(tool_call, dict) else None

    if intent_class in TOOL_INTENTS and not isinstance(tool_name, str):
        return "tool intent has null tool_call"

    if intent_class in NULL_INTENTS and tool_call is not None:
        return "null intent has non-null tool_call"

    return None


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)

    raw_records = _load_jsonl(input_path)

    dedup = NearDuplicateIndex(ratio_threshold=args.dedup_threshold)
    output_records: list[dict] = []

    schema_rejected = 0
    contract_rejected = 0
    duplicate_rejected = 0
    critic_disagreements = 0

    for raw in raw_records:
        record = deep_copy_record(raw)

        shape_errors = validate_record_shape(record)
        if shape_errors:
            schema_rejected += 1
            continue

        user_text = str(record["user_text"]).strip()
        intent_class = str(record["intent_class"])

        canonical_target = canonicalize_target(user_text=user_text, target=record["target"])
        canonical_target["assistant_text"] = deterministic_assistant_text(
            intent_class=intent_class,
            tool_call=canonical_target.get("tool_call"),
        )
        record["target"] = canonical_target

        alignment_error = _intent_target_alignment_error(record)
        if alignment_error is not None:
            contract_rejected += 1
            continue

        contract_errors = validate_record_contract(record)
        if contract_errors:
            contract_rejected += 1
            continue

        critic_target = infer_critic_target(user_text=user_text, intent_class=intent_class)
        critic_pass = targets_match(record["target"], critic_target)
        if not critic_pass:
            critic_disagreements += 1

        target_sig = target_signature(record["target"])
        keep = dedup.add_if_new(
            text=user_text,
            intent_class=intent_class,
            target_sig=target_sig,
        )
        if not keep:
            duplicate_rejected += 1
            continue

        quality = record.get("quality")
        if not isinstance(quality, dict):
            quality = {}
            record["quality"] = quality
        quality["validator_pass"] = True
        quality["critic_pass"] = critic_pass
        quality["human_reviewed"] = bool(quality.get("human_reviewed", False))
        quality["human_label_ok"] = bool(quality.get("human_label_ok", False))

        output_records.append(record)

    write_jsonl(output_path, output_records)

    summary = ValidationSummary(
        total_in=len(raw_records),
        total_out=len(output_records),
        schema_rejected=schema_rejected,
        contract_rejected=contract_rejected,
        duplicate_rejected=duplicate_rejected,
        critic_disagreements=critic_disagreements,
    )

    report = {
        "generated_at": utc_now_iso(),
        "input_path": str(input_path.resolve()),
        "output_path": str(output_path.resolve()),
        "total_in": summary.total_in,
        "total_out": summary.total_out,
        "schema_rejected": summary.schema_rejected,
        "contract_rejected": summary.contract_rejected,
        "duplicate_rejected": summary.duplicate_rejected,
        "critic_disagreements": summary.critic_disagreements,
        "critic_disagreement_ratio": (
            round(summary.critic_disagreements / summary.total_out, 6)
            if summary.total_out
            else 0.0
        ),
    }

    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(stable_json_dumps(report), encoding="utf-8")

    print(f"Validated {summary.total_out}/{summary.total_in} records -> {output_path}")
    print(f"Report -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

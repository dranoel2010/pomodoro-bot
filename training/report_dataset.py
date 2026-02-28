#!/usr/bin/env python3
"""Generate dataset quality and class-balance reports for finalized splits."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.common import (
    class_minimum_failures,
    stable_json_dumps,
    tool_vs_null_ratio,
    utc_now_iso,
    validate_record_contract,
    validate_record_shape,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report finalized dataset quality")
    parser.add_argument("--in", dest="input_dir", required=True)
    parser.add_argument("--out", dest="quality_out", required=True)
    parser.add_argument(
        "--class-balance-out",
        default="",
        help="Optional class-balance output path (default: sibling class_balance_report_v1.json)",
    )
    parser.add_argument("--min-per-class", type=int, default=100)
    parser.add_argument(
        "--review-report",
        default="training/reports/review_outcomes_v1.json",
        help="Optional review outcomes report to embed in quality report",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_no} in {path} is not an object")
            rows.append(value)
    return rows


def _collect_records(input_dir: Path) -> dict[str, list[dict[str, Any]]]:
    by_split: dict[str, list[dict[str, Any]]] = {}
    for split in ("train", "val", "test"):
        path = input_dir / f"{split}.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"Missing split file: {path}")
        by_split[split] = _load_jsonl(path)
    return by_split


def main() -> int:
    args = _parse_args()
    input_dir = Path(args.input_dir)
    splits = _collect_records(input_dir)

    all_records: list[dict[str, Any]] = []
    for rows in splits.values():
        all_records.extend(rows)

    shape_errors = 0
    contract_errors = 0
    source_counter: Counter[str] = Counter()
    noise_counter: Counter[str] = Counter()
    intent_counter: Counter[str] = Counter()
    split_counter: Counter[str] = Counter()
    per_split_intents: dict[str, Counter[str]] = defaultdict(Counter)

    for split, rows in splits.items():
        split_counter[split] = len(rows)
        for row in rows:
            intent = str(row.get("intent_class") or "")
            intent_counter[intent] += 1
            per_split_intents[split][intent] += 1

            source = row.get("source")
            if isinstance(source, str):
                source_counter[source] += 1

            noise_tags = row.get("noise_tags")
            if isinstance(noise_tags, list):
                for tag in noise_tags:
                    if isinstance(tag, str):
                        noise_counter[tag] += 1

            shape = validate_record_shape(row)
            if shape:
                shape_errors += 1
                continue

            contract = validate_record_contract(row)
            if contract:
                contract_errors += 1

    tool_count, null_count = tool_vs_null_ratio(all_records)
    total = len(all_records)

    quality_report = {
        "generated_at": utc_now_iso(),
        "input_dir": str(input_dir.resolve()),
        "total_records": total,
        "split_sizes": dict(split_counter),
        "tool_count": tool_count,
        "null_count": null_count,
        "tool_ratio": round(tool_count / total, 6) if total else 0.0,
        "null_ratio": round(null_count / total, 6) if total else 0.0,
        "shape_error_count": shape_errors,
        "contract_error_count": contract_errors,
        "source_distribution": dict(sorted(source_counter.items())),
        "noise_distribution": dict(sorted(noise_counter.items())),
    }

    review_path = Path(args.review_report)
    if review_path.exists():
        try:
            review_payload = json.loads(review_path.read_text(encoding="utf-8"))
            if isinstance(review_payload, dict):
                quality_report["review_gate"] = review_payload.get("gate")
                quality_report["reviewed_count"] = review_payload.get("reviewed_count")
                quality_report["acceptance_rate"] = review_payload.get("acceptance_rate")
        except json.JSONDecodeError:
            quality_report["review_gate"] = {"pass": False, "reasons": ["invalid review report JSON"]}

    balance_failures = class_minimum_failures(all_records, minimum=args.min_per_class)
    class_balance_report = {
        "generated_at": utc_now_iso(),
        "input_dir": str(input_dir.resolve()),
        "min_per_class": args.min_per_class,
        "intent_counts": dict(sorted(intent_counter.items())),
        "per_split_intents": {
            split: dict(sorted(counter.items()))
            for split, counter in sorted(per_split_intents.items())
        },
        "below_minimum": dict(sorted(balance_failures.items())),
    }

    quality_path = Path(args.quality_out)
    quality_path.parent.mkdir(parents=True, exist_ok=True)
    quality_path.write_text(stable_json_dumps(quality_report), encoding="utf-8")

    class_balance_out = (
        Path(args.class_balance_out)
        if args.class_balance_out.strip()
        else quality_path.with_name("class_balance_report_v1.json")
    )
    class_balance_out.parent.mkdir(parents=True, exist_ok=True)
    class_balance_out.write_text(stable_json_dumps(class_balance_report), encoding="utf-8")

    print(f"Data quality report -> {quality_path}")
    print(f"Class balance report -> {class_balance_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

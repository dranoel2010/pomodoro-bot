#!/usr/bin/env python3
"""Build a manual review queue from validated records."""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.common import FAILURE_PRONE_INTENTS, stable_json_dumps, utc_now_iso, write_jsonl


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build manual review queue")
    parser.add_argument("--in", dest="input_path", required=True)
    parser.add_argument("--out", dest="output_path", required=True)
    parser.add_argument("--size", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument(
        "--report-out",
        default="training/reports/review_queue_report_v1.json",
        help="Queue report JSON path",
    )
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    import json

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


def _annotate_review_fields(record: dict[str, Any], *, bucket: str) -> dict[str, Any]:
    clone = __import__("json").loads(stable_json_dumps(record))
    clone["review_priority"] = bucket
    clone["review"] = {
        "action": "",
        "notes": "",
        "fixed_target": None,
    }
    return clone


def main() -> int:
    args = _parse_args()
    if args.size < 1:
        raise ValueError("--size must be >= 1")

    rng = random.Random(args.seed)
    records = _load_jsonl(Path(args.input_path))

    disagreements = [
        record
        for record in records
        if not bool(record.get("quality", {}).get("critic_pass", False))
    ]

    failure_prone = [
        record
        for record in records
        if str(record.get("intent_class")) in FAILURE_PRONE_INTENTS
    ]

    all_records = list(records)

    disagree_target = int(round(args.size * 0.60))
    failure_target = int(round(args.size * 0.25))
    random_target = max(0, args.size - disagree_target - failure_target)

    selected_ids: set[str] = set()
    queue: list[dict[str, Any]] = []

    rng.shuffle(disagreements)
    for record in disagreements:
        if len(queue) >= disagree_target:
            break
        record_id = str(record.get("id"))
        if record_id in selected_ids:
            continue
        queue.append(_annotate_review_fields(record, bucket="critic_disagreement"))
        selected_ids.add(record_id)

    rng.shuffle(failure_prone)
    for record in failure_prone:
        if len(queue) >= disagree_target + failure_target:
            break
        record_id = str(record.get("id"))
        if record_id in selected_ids:
            continue
        queue.append(_annotate_review_fields(record, bucket="failure_prone"))
        selected_ids.add(record_id)

    rng.shuffle(all_records)
    for record in all_records:
        if len(queue) >= args.size:
            break
        record_id = str(record.get("id"))
        if record_id in selected_ids:
            continue
        queue.append(_annotate_review_fields(record, bucket="random_sanity"))
        selected_ids.add(record_id)

    if len(queue) < args.size:
        raise ValueError(
            f"Could only build queue with {len(queue)} records, requested {args.size}"
        )

    out_path = Path(args.output_path)
    write_jsonl(out_path, queue)

    bucket_counts: dict[str, int] = {}
    for row in queue:
        bucket = str(row.get("review_priority"))
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    report = {
        "generated_at": utc_now_iso(),
        "input_path": str(Path(args.input_path).resolve()),
        "output_path": str(out_path.resolve()),
        "requested_size": args.size,
        "selected_size": len(queue),
        "bucket_counts": bucket_counts,
        "disagreement_pool": len(disagreements),
        "failure_prone_pool": len(failure_prone),
    }

    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(stable_json_dumps(report), encoding="utf-8")

    print(f"Built review queue with {len(queue)} records -> {out_path}")
    print(f"Report -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

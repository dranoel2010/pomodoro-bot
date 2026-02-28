#!/usr/bin/env python3
"""Finalize reviewed records into train/val/test splits."""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.common import (
    DEFAULT_SPLIT_SIZES,
    TARGET_DATASET_SIZE,
    allocate_counts,
    canonicalize_target,
    deterministic_assistant_text,
    intent_distribution,
    stable_json_dumps,
    stratified_split,
    tool_vs_null_ratio,
    utc_now_iso,
    write_jsonl,
)


VALID_REVIEW_ACTIONS = {"accept", "fix", "reject"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize reviewed dataset into train/val/test")
    parser.add_argument("--validated", required=True)
    parser.add_argument("--reviewed", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--target-size", type=int, default=TARGET_DATASET_SIZE)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--min-reviewed", type=int, default=2000)
    parser.add_argument("--acceptance-threshold", type=float, default=0.97)
    parser.add_argument("--per-intent-threshold", type=float, default=0.95)
    parser.add_argument(
        "--review-report",
        default="training/reports/review_outcomes_v1.json",
        help="Review outcome report path",
    )
    parser.add_argument(
        "--allow-gate-failure",
        action="store_true",
        help="Write outputs even when review gate fails",
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


def _review_decisions(reviewed_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for row in reviewed_records:
        rec_id = row.get("id")
        if not isinstance(rec_id, str) or not rec_id:
            continue

        review = row.get("review")
        if not isinstance(review, dict):
            continue

        action_raw = review.get("action")
        if not isinstance(action_raw, str):
            continue
        action = action_raw.strip().lower()
        if action not in VALID_REVIEW_ACTIONS:
            continue

        decisions[rec_id] = {
            "action": action,
            "fixed_target": review.get("fixed_target"),
            "intent_class": row.get("intent_class"),
        }
    return decisions


def _stratified_sample(records: list[dict[str, Any]], *, target_size: int, seed: int) -> list[dict[str, Any]]:
    if target_size > len(records):
        raise ValueError(
            f"Cannot sample {target_size} from {len(records)} accepted records"
        )

    rng = random.Random(seed)
    by_intent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_intent[str(record["intent_class"])].append(record)

    for values in by_intent.values():
        rng.shuffle(values)

    counts_available = {intent: len(values) for intent, values in by_intent.items()}
    desired = allocate_counts({k: float(v) for k, v in counts_available.items()}, target_size)

    # Repair any over-allocation caused by rounding edge cases.
    overflow = 0
    for intent, wanted in list(desired.items()):
        available = counts_available[intent]
        if wanted > available:
            overflow += wanted - available
            desired[intent] = available

    if overflow > 0:
        intents_by_capacity = sorted(
            counts_available,
            key=lambda key: counts_available[key] - desired[key],
            reverse=True,
        )
        for intent in intents_by_capacity:
            if overflow == 0:
                break
            capacity = counts_available[intent] - desired[intent]
            if capacity <= 0:
                continue
            delta = min(capacity, overflow)
            desired[intent] += delta
            overflow -= delta

    selected: list[dict[str, Any]] = []
    for intent, wanted in desired.items():
        selected.extend(by_intent[intent][:wanted])

    if len(selected) != target_size:
        raise ValueError(f"Sampling mismatch: expected {target_size}, got {len(selected)}")

    rng.shuffle(selected)
    return selected


def main() -> int:
    args = _parse_args()
    validated = _load_jsonl(Path(args.validated))
    reviewed = _load_jsonl(Path(args.reviewed))

    decisions = _review_decisions(reviewed)

    reviewed_count = 0
    accepted_count = 0
    per_intent_review: dict[str, Counter[str]] = defaultdict(Counter)

    accepted_records: list[dict[str, Any]] = []
    unresolved_disagreements = 0

    for row in validated:
        record = json.loads(stable_json_dumps(row))
        rec_id = str(record.get("id") or "")
        if not rec_id:
            continue

        quality = record.get("quality")
        if not isinstance(quality, dict):
            quality = {}
            record["quality"] = quality

        decision = decisions.get(rec_id)
        reviewed_action = None
        if decision is not None:
            reviewed_action = decision["action"]
            reviewed_count += 1
            intent = str(record.get("intent_class") or "")
            per_intent_review[intent][reviewed_action] += 1

            if reviewed_action == "reject":
                quality["human_reviewed"] = True
                quality["human_label_ok"] = False
                continue

            if reviewed_action == "fix":
                fixed_target = decision.get("fixed_target")
                if isinstance(fixed_target, dict):
                    canonical = canonicalize_target(
                        user_text=str(record["user_text"]),
                        target=fixed_target,
                    )
                    canonical["assistant_text"] = deterministic_assistant_text(
                        intent_class=str(record["intent_class"]),
                        tool_call=canonical.get("tool_call"),
                    )
                    record["target"] = canonical
                quality["human_reviewed"] = True
                quality["human_label_ok"] = True
                accepted_count += 1

            if reviewed_action == "accept":
                quality["human_reviewed"] = True
                quality["human_label_ok"] = True
                accepted_count += 1

        critic_pass = bool(quality.get("critic_pass", False))
        if not critic_pass and reviewed_action not in {"accept", "fix"}:
            unresolved_disagreements += 1
            continue

        if not bool(quality.get("validator_pass", False)):
            continue

        accepted_records.append(record)

    acceptance_rate = (accepted_count / reviewed_count) if reviewed_count else 0.0

    per_intent_acceptance: dict[str, float] = {}
    low_intent_acceptance: dict[str, float] = {}
    for intent, counts in per_intent_review.items():
        reviewed_intent = sum(counts.values())
        accepted_intent = counts.get("accept", 0) + counts.get("fix", 0)
        rate = (accepted_intent / reviewed_intent) if reviewed_intent else 0.0
        per_intent_acceptance[intent] = rate
        if rate < args.per_intent_threshold:
            low_intent_acceptance[intent] = rate

    gate_pass = True
    gate_reasons: list[str] = []
    if reviewed_count < args.min_reviewed:
        gate_pass = False
        gate_reasons.append(
            f"reviewed_count {reviewed_count} < required {args.min_reviewed}"
        )
    if acceptance_rate < args.acceptance_threshold:
        gate_pass = False
        gate_reasons.append(
            f"acceptance_rate {acceptance_rate:.4f} < required {args.acceptance_threshold:.4f}"
        )
    if low_intent_acceptance:
        gate_pass = False
        gate_reasons.append(
            f"per-intent acceptance below threshold for {sorted(low_intent_acceptance)}"
        )
    if unresolved_disagreements > 0:
        gate_pass = False
        gate_reasons.append(
            f"{unresolved_disagreements} critic disagreements unresolved by review"
        )

    sampled = _stratified_sample(
        accepted_records,
        target_size=args.target_size,
        seed=args.seed,
    )

    split_sizes = dict(DEFAULT_SPLIT_SIZES)
    if args.target_size != TARGET_DATASET_SIZE:
        split_sizes = {
            "train": int(round(args.target_size * 0.80)),
            "val": int(round(args.target_size * 0.10)),
            "test": args.target_size
            - int(round(args.target_size * 0.80))
            - int(round(args.target_size * 0.10)),
        }

    split_rows = stratified_split(sampled, split_sizes=split_sizes, seed=args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_path = out_dir / "train.jsonl"
    val_path = out_dir / "val.jsonl"
    test_path = out_dir / "test.jsonl"

    write_jsonl(train_path, split_rows["train"])
    write_jsonl(val_path, split_rows["val"])
    write_jsonl(test_path, split_rows["test"])

    intent_counts = intent_distribution(sampled)
    tool_count, null_count = tool_vs_null_ratio(sampled)

    review_report = {
        "generated_at": utc_now_iso(),
        "validated_path": str(Path(args.validated).resolve()),
        "reviewed_path": str(Path(args.reviewed).resolve()),
        "output_dir": str(out_dir.resolve()),
        "target_size": args.target_size,
        "accepted_pool_size": len(accepted_records),
        "reviewed_count": reviewed_count,
        "accepted_review_count": accepted_count,
        "acceptance_rate": round(acceptance_rate, 6),
        "per_intent_acceptance": {
            key: round(value, 6)
            for key, value in sorted(per_intent_acceptance.items())
        },
        "low_intent_acceptance": {
            key: round(value, 6)
            for key, value in sorted(low_intent_acceptance.items())
        },
        "unresolved_disagreements": unresolved_disagreements,
        "gate": {
            "pass": gate_pass,
            "reasons": gate_reasons,
            "min_reviewed": args.min_reviewed,
            "acceptance_threshold": args.acceptance_threshold,
            "per_intent_threshold": args.per_intent_threshold,
        },
        "final_distribution": {
            "tool_count": tool_count,
            "null_count": null_count,
            "intent_counts": dict(sorted(intent_counts.items())),
            "split_sizes": {split: len(rows) for split, rows in split_rows.items()},
        },
    }

    review_report_path = Path(args.review_report)
    review_report_path.parent.mkdir(parents=True, exist_ok=True)
    review_report_path.write_text(stable_json_dumps(review_report), encoding="utf-8")

    print(f"Wrote final splits to {out_dir}")
    print(f"Review outcomes report -> {review_report_path}")

    if not gate_pass and not args.allow_gate_failure:
        raise SystemExit(
            "Review gate failed. Inspect training/reports/review_outcomes_v1.json and regenerate low-quality classes."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

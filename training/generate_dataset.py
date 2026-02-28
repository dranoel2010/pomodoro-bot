#!/usr/bin/env python3
"""Generate raw candidate records for tool-call fine-tuning."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from training.common import (
    NULL_INTENTS,
    PRIORITY_TOOL_INTENTS,
    TOOL_INTENTS,
    allocate_counts,
    canonicalize_target,
    deterministic_assistant_text,
    infer_critic_target,
    stable_json_dumps,
    targets_match,
    utc_now_iso,
    write_jsonl,
)
from training.noise import apply_noise
from training.teacher import TeacherClient
from training.templates import SeedExample, build_seed_example


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate raw tool-call training candidates")
    parser.add_argument("--target-size", type=int, required=True, help="Target final dataset size")
    parser.add_argument("--teacher", required=True, help="Teacher model id (metadata + API model)")
    parser.add_argument(
        "--teacher-provider",
        default="auto",
        choices=("auto", "openai", "ollama", "local"),
        help="Teacher paraphrase provider",
    )
    parser.add_argument(
        "--out",
        default="training/data/raw_candidates.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument(
        "--report-out",
        default="training/reports/generate_report_v1.json",
        help="Generation report path",
    )
    parser.add_argument(
        "--oversample-factor",
        type=float,
        default=2.00,
        help="Generate this factor above target size to absorb later filtering",
    )
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument(
        "--teacher-share",
        type=float,
        default=0.35,
        help="Fraction of examples that receive teacher paraphrase",
    )
    parser.add_argument(
        "--noise-share",
        type=float,
        default=0.55,
        help="Fraction of examples that receive ASR-like noise",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="Progress log cadence in records (0 = auto)",
    )
    return parser.parse_args()


def _distribution_for_raw_target(raw_target_size: int) -> dict[str, int]:
    tool_count = int(round(raw_target_size * 0.70))
    null_count = raw_target_size - tool_count

    tool_weights = {
        intent: (1.6 if intent in PRIORITY_TOOL_INTENTS else 1.0)
        for intent in TOOL_INTENTS
    }
    null_weights = {
        "null_prompt_injection": 1.4,
        "null_ambiguous": 1.4,
        "null_calendar_missing_slot": 1.3,
        "null_identity": 1.0,
        "null_gratitude": 1.0,
        "null_smalltalk": 1.0,
        "null_timer_status_question": 1.0,
        "null_definition_pomodoro": 1.0,
    }

    tool_alloc = allocate_counts(tool_weights, tool_count)
    null_alloc = allocate_counts(null_weights, null_count)

    merged = dict(tool_alloc)
    merged.update(null_alloc)
    return merged


def _provisional_split(record_id: str) -> str:
    digest = hashlib.sha1(record_id.encode("utf-8")).hexdigest()
    value = int(digest[-2:], 16) % 10
    if value <= 7:
        return "train"
    if value == 8:
        return "val"
    return "test"


def _build_record(
    *,
    seed_example: SeedExample,
    index: int,
    user_text: str,
    noise_tags: list[str],
    teacher_used: bool,
    teacher_model: str,
    created_at: str,
) -> dict[str, Any]:
    canonical_target = canonicalize_target(user_text=user_text, target=seed_example.target)
    canonical_target["assistant_text"] = deterministic_assistant_text(
        intent_class=seed_example.intent_class,
        tool_call=canonical_target.get("tool_call"),
    )
    critic_target = infer_critic_target(user_text=user_text, intent_class=seed_example.intent_class)
    critic_pass = targets_match(canonical_target, critic_target)

    if seed_example.hard_negative:
        source = "hard_negative"
    elif teacher_used:
        source = "teacher"
    elif noise_tags:
        source = "mutation"
    else:
        source = "template"

    record_id = f"r{index:07d}_{seed_example.intent_class}"
    return {
        "id": record_id,
        "split": _provisional_split(record_id),
        "user_text": user_text,
        "target": canonical_target,
        "intent_class": seed_example.intent_class,
        "noise_tags": noise_tags,
        "source": source,
        "quality": {
            "validator_pass": False,
            "critic_pass": critic_pass,
            "human_reviewed": False,
            "human_label_ok": False,
        },
        "provenance": {
            "template_id": seed_example.template_id,
            "generator_model": teacher_model,
            "created_at": created_at,
        },
    }


def main() -> int:
    args = _parse_args()
    if args.target_size < 1:
        raise ValueError("--target-size must be >= 1")

    rng = random.Random(args.seed)
    raw_target_size = int(math.ceil(args.target_size * args.oversample_factor))
    counts = _distribution_for_raw_target(raw_target_size)
    total_to_generate = sum(counts.values())

    teacher = TeacherClient(model=args.teacher, provider=args.teacher_provider)
    created_at = utc_now_iso()

    records: list[dict[str, Any]] = []
    teacher_hits = 0
    noise_hits = 0
    started_at = time.perf_counter()
    progress_every = args.progress_every if args.progress_every > 0 else max(1000, total_to_generate // 100)

    print(
        f"Starting generation: target={args.target_size} raw_target={total_to_generate} "
        f"teacher_provider={args.teacher_provider} teacher={args.teacher}",
        flush=True,
    )

    idx = 0
    for intent_class, count in sorted(counts.items()):
        for local_index in range(count):
            idx += 1
            seed_example = build_seed_example(intent_class=intent_class, rng=rng, index=local_index)

            user_text = seed_example.user_text
            teacher_used = False
            if rng.random() < args.teacher_share:
                tool_call = seed_example.target.get("tool_call")
                tool_name = tool_call.get("name") if isinstance(tool_call, dict) else None
                paraphrased, teacher_used = teacher.paraphrase(
                    user_text=user_text,
                    intent_class=seed_example.intent_class,
                    target_tool_name=tool_name if isinstance(tool_name, str) else None,
                    rng=rng,
                )
                user_text = paraphrased
                if teacher_used:
                    teacher_hits += 1

            enable_noise = rng.random() < args.noise_share
            user_text, noise_tags = apply_noise(user_text, rng=rng, enabled=enable_noise)
            if noise_tags:
                noise_hits += 1

            record = _build_record(
                seed_example=seed_example,
                index=idx,
                user_text=user_text,
                noise_tags=noise_tags,
                teacher_used=teacher_used,
                teacher_model=args.teacher,
                created_at=created_at,
            )
            records.append(record)

            if idx % progress_every == 0 or idx == total_to_generate:
                elapsed = max(time.perf_counter() - started_at, 1e-9)
                rate = idx / elapsed
                remaining = max(total_to_generate - idx, 0)
                eta = remaining / rate if rate > 0 else 0.0
                percent = (idx / total_to_generate) * 100.0 if total_to_generate else 100.0
                print(
                    "progress(generate): "
                    f"{idx}/{total_to_generate} ({percent:.1f}%) "
                    f"rate={rate:.1f} rec/s eta={eta:.1f}s "
                    f"teacher_hits={teacher_hits} noise_hits={noise_hits}",
                    flush=True,
                )

    rng.shuffle(records)

    out_path = Path(args.out)
    wrote = write_jsonl(out_path, records)

    by_intent = Counter(record["intent_class"] for record in records)
    by_source = Counter(record["source"] for record in records)

    report = {
        "generated_at": utc_now_iso(),
        "target_size": args.target_size,
        "raw_target_size": raw_target_size,
        "written_records": wrote,
        "teacher_model": args.teacher,
        "teacher_provider": args.teacher_provider,
        "teacher_hits": teacher_hits,
        "noise_hits": noise_hits,
        "counts_by_intent": dict(sorted(by_intent.items())),
        "counts_by_source": dict(sorted(by_source.items())),
        "output_path": str(out_path.resolve()),
    }

    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(stable_json_dumps(report), encoding="utf-8")

    print(f"Generated {wrote} records -> {out_path}")
    print(f"Report -> {report_path}")
    if args.teacher_provider == "ollama" and teacher_hits == 0:
        print(
            "Warning: teacher_provider=ollama but no successful teacher paraphrases were recorded. "
            "Check that Ollama is running and the model is available."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

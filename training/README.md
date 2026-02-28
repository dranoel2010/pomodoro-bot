# Training Data Pipeline (v1)

This directory contains a full data-first pipeline for high-quality tool-call supervision.

## Outputs

- `training/data/raw_candidates.jsonl`
- `training/data/validated.jsonl`
- `training/data/review_queue.jsonl`
- `training/data/final/train.jsonl`
- `training/data/final/val.jsonl`
- `training/data/final/test.jsonl`
- `training/reports/data_quality_report_v1.json`
- `training/reports/class_balance_report_v1.json`
- `training/reports/review_outcomes_v1.json`

## Public Record Contract

- JSON schema: `training/data/schema_v1.json`
- Top-level fields:
  - `id`
  - `split`
  - `user_text`
  - `target`
  - `intent_class`
  - `noise_tags`
  - `source`
  - `quality`
  - `provenance`

## CLI Workflow

Generate raw candidates:

```bash
uv run python training/generate_dataset.py --target-size 60000 --teacher <model_id>
```

Validate and filter:

```bash
uv run python training/validate_dataset.py --in training/data/raw_candidates.jsonl --out training/data/validated.jsonl
```

Build review queue:

```bash
uv run python training/build_review_queue.py --in training/data/validated.jsonl --out training/data/review_queue.jsonl --size 2000
```

Finalize reviewed data:

```bash
uv run python training/finalize_dataset.py --validated training/data/validated.jsonl --reviewed training/data/review_queue_reviewed.jsonl --out-dir training/data/final
```

Generate final reports:

```bash
uv run python training/report_dataset.py --in training/data/final --out training/reports/data_quality_report_v1.json
```

## Review File Format

`finalize_dataset.py` expects the reviewed file to contain all queue rows plus:

- `review.action`: `accept`, `fix`, or `reject`
- `review.notes`: optional free text
- `review.fixed_target`: required when `action=fix`

Queue builder initializes these fields as empty placeholders.

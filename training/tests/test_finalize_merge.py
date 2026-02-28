from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from training.common import deterministic_assistant_text


class FinalizeMergeTests(unittest.TestCase):
    def _record(self, idx: int, *, intent_class: str, user_text: str, tool_call, critic_pass: bool) -> dict:
        return {
            "id": f"r{idx:04d}",
            "split": "train",
            "user_text": user_text,
            "target": {
                "assistant_text": deterministic_assistant_text(
                    intent_class=intent_class,
                    tool_call=tool_call,
                ),
                "tool_call": tool_call,
            },
            "intent_class": intent_class,
            "noise_tags": [],
            "source": "template",
            "quality": {
                "validator_pass": True,
                "critic_pass": critic_pass,
                "human_reviewed": False,
                "human_label_ok": False,
            },
            "provenance": {
                "template_id": "t",
                "generator_model": "teacher",
                "created_at": "2026-02-28T12:00:00+00:00",
            },
        }

    def test_finalize_applies_fix_and_writes_splits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            validated_path = tmp / "validated.jsonl"
            reviewed_path = tmp / "reviewed.jsonl"
            out_dir = tmp / "final"
            review_report = tmp / "review_report.json"

            validated_rows = []
            for idx in range(1, 12):
                validated_rows.append(
                    self._record(
                        idx,
                        intent_class="start_timer",
                        user_text=f"Starte Timer {idx}",
                        tool_call={"name": "start_timer", "arguments": {"duration": "10"}},
                        critic_pass=True,
                    )
                )

            # One disagreement that must be fixed by human review.
            validated_rows.append(
                self._record(
                    99,
                    intent_class="start_timer",
                    user_text="Starte Timer fuer 25 Minuten",
                    tool_call={"name": "start_timer", "arguments": {"duration": "10"}},
                    critic_pass=False,
                )
            )

            with validated_path.open("w", encoding="utf-8") as handle:
                for row in validated_rows:
                    handle.write(json.dumps(row, ensure_ascii=False))
                    handle.write("\n")

            reviewed_rows = [
                {
                    **validated_rows[-1],
                    "review": {
                        "action": "fix",
                        "notes": "duration corrected",
                        "fixed_target": {
                            "assistant_text": "",
                            "tool_call": {
                                "name": "start_timer",
                                "arguments": {"duration": "25m"},
                            },
                        },
                    },
                }
            ]
            with reviewed_path.open("w", encoding="utf-8") as handle:
                for row in reviewed_rows:
                    handle.write(json.dumps(row, ensure_ascii=False))
                    handle.write("\n")

            cmd = [
                "python",
                "training/finalize_dataset.py",
                "--validated",
                str(validated_path),
                "--reviewed",
                str(reviewed_path),
                "--out-dir",
                str(out_dir),
                "--target-size",
                "10",
                "--min-reviewed",
                "1",
                "--acceptance-threshold",
                "0.5",
                "--per-intent-threshold",
                "0.0",
                "--review-report",
                str(review_report),
            ]
            subprocess.run(cmd, check=True)

            self.assertTrue((out_dir / "train.jsonl").exists())
            self.assertTrue((out_dir / "val.jsonl").exists())
            self.assertTrue((out_dir / "test.jsonl").exists())

            report = json.loads(review_report.read_text(encoding="utf-8"))
            self.assertTrue(report["gate"]["pass"])
            self.assertEqual(1, report["reviewed_count"])


if __name__ == "__main__":
    unittest.main()

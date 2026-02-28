from __future__ import annotations

import unittest

from training.common import (
    NearDuplicateIndex,
    class_minimum_failures,
    deterministic_assistant_text,
    stratified_split,
)


def _make_record(idx: int, intent_class: str, user_text: str, tool_call: dict | None) -> dict:
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
            "critic_pass": True,
            "human_reviewed": False,
            "human_label_ok": False,
        },
        "provenance": {
            "template_id": "t",
            "generator_model": "teacher",
            "created_at": "2026-02-28T12:00:00+00:00",
        },
    }


class DedupAndSplitTests(unittest.TestCase):
    def test_near_duplicate_index_rejects_similar_text(self) -> None:
        dedup = NearDuplicateIndex(ratio_threshold=0.90)
        target_sig = '{"assistant_text":"x","tool_call":null}'
        self.assertTrue(
            dedup.add_if_new(
                text="Pausiere den Timer bitte jetzt.",
                intent_class="pause_timer",
                target_sig=target_sig,
            )
        )
        self.assertFalse(
            dedup.add_if_new(
                text="Pausiere den Timer bitte jetzt",
                intent_class="pause_timer",
                target_sig=target_sig,
            )
        )

    def test_stratified_split_exact_counts(self) -> None:
        records = []
        for i in range(6):
            records.append(
                _make_record(i, "start_timer", f"start {i}", {"name": "start_timer", "arguments": {"duration": "10"}})
            )
        for i in range(6, 10):
            records.append(
                _make_record(i, "null_identity", f"identity {i}", None)
            )

        splits = stratified_split(
            records,
            split_sizes={"train": 8, "val": 1, "test": 1},
            seed=42,
        )
        self.assertEqual(8, len(splits["train"]))
        self.assertEqual(1, len(splits["val"]))
        self.assertEqual(1, len(splits["test"]))

        all_split_values = {row["split"] for rows in splits.values() for row in rows}
        self.assertEqual({"train", "val", "test"}, all_split_values)

    def test_class_minimum_failures(self) -> None:
        records = [
            _make_record(1, "start_timer", "a", {"name": "start_timer", "arguments": {"duration": "10"}}),
            _make_record(2, "start_timer", "b", {"name": "start_timer", "arguments": {"duration": "10"}}),
            _make_record(3, "null_identity", "c", None),
        ]
        failures = class_minimum_failures(records, minimum=2)
        self.assertEqual({"null_identity": 1}, failures)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import re
import unittest

from training.common import (
    TOOL_ADD_CALENDAR_EVENT,
    deterministic_assistant_text,
    validate_record_contract,
    validate_record_shape,
    canonicalize_target,
)


def _record(*, tool_call, intent_class: str) -> dict:
    return {
        "id": "r0001",
        "split": "train",
        "user_text": "test",
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
            "template_id": "t1",
            "generator_model": "teacher",
            "created_at": "2026-02-28T12:00:00+00:00",
        },
    }


class CommonContractTests(unittest.TestCase):
    def test_shape_valid_for_tool_record(self) -> None:
        record = _record(
            tool_call={"name": "start_timer", "arguments": {"duration": "25m"}},
            intent_class="start_timer",
        )
        self.assertEqual([], validate_record_shape(record))

    def test_shape_valid_for_null_record(self) -> None:
        record = _record(tool_call=None, intent_class="null_identity")
        self.assertEqual([], validate_record_shape(record))

    def test_contract_rejects_missing_required_argument(self) -> None:
        record = _record(
            tool_call={"name": "start_timer", "arguments": {}},
            intent_class="start_timer",
        )
        errors = validate_record_contract(record)
        self.assertTrue(any("required argument" in err for err in errors))

    def test_contract_rejects_non_iso_calendar_time(self) -> None:
        record = _record(
            tool_call={
                "name": TOOL_ADD_CALENDAR_EVENT,
                "arguments": {
                    "title": "Review",
                    "start_time": "morgen 10 uhr",
                },
            },
            intent_class=TOOL_ADD_CALENDAR_EVENT,
        )
        errors = validate_record_contract(record)
        self.assertTrue(any("ISO-8601" in err for err in errors))

    def test_calendar_normalization_is_deterministic(self) -> None:
        target = {
            "assistant_text": "",
            "tool_call": {
                "name": TOOL_ADD_CALENDAR_EVENT,
                "arguments": {
                    "title": "Architektur Review",
                    "start_time": "21.03.2026 14:15",
                },
            },
        }
        normalized = canonicalize_target(
            user_text="Fuege Termin Architektur Review am 21.03.2026 um 14:15 hinzu.",
            target=target,
        )

        tool_call = normalized["tool_call"]
        self.assertIsInstance(tool_call, dict)
        if not isinstance(tool_call, dict):
            self.fail("tool_call not present after normalization")
        start_time = tool_call["arguments"]["start_time"]
        self.assertRegex(start_time, r"^2026-03-21T14:15[+-]\d{2}:\d{2}$")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import datetime as dt
import unittest

from shared.time_parsing import (
    duration_seconds_from_value,
    normalize_datetime_input,
    normalize_duration_token,
    parse_datetime_input,
)


class TimeParsingTests(unittest.TestCase):
    def test_normalize_duration_token_supports_common_inputs(self) -> None:
        self.assertEqual("15", normalize_duration_token(15))
        self.assertEqual("15m", normalize_duration_token("15 Minuten"))
        self.assertEqual("90s", normalize_duration_token("90s"))
        self.assertEqual("2h", normalize_duration_token("2h"))
        self.assertIsNone(normalize_duration_token("n/a"))

    def test_duration_seconds_from_value_supports_common_units(self) -> None:
        self.assertEqual(15 * 60, duration_seconds_from_value("15", default_seconds=30))
        self.assertEqual(90, duration_seconds_from_value("90s", default_seconds=30))
        self.assertEqual(2 * 3600, duration_seconds_from_value("2h", default_seconds=30))
        self.assertEqual(7 * 60, duration_seconds_from_value(7, default_seconds=30))
        self.assertEqual(30, duration_seconds_from_value(None, default_seconds=30))

    def test_parse_datetime_input_parses_relative_and_german_formats(self) -> None:
        fixed_now = dt.datetime(2026, 2, 21, 10, 0, tzinfo=dt.timezone.utc)
        relative = parse_datetime_input("morgen 9 Uhr", now_fn=lambda: fixed_now)
        absolute = parse_datetime_input("22.02.2026 09:15")

        self.assertEqual(
            dt.datetime(2026, 2, 22, 9, 0, tzinfo=dt.timezone.utc),
            relative,
        )
        self.assertIsNotNone(absolute)
        if absolute is None:
            self.fail("Expected German datetime input to parse.")
        self.assertEqual(2026, absolute.year)
        self.assertEqual(2, absolute.month)
        self.assertEqual(22, absolute.day)
        self.assertEqual(9, absolute.hour)
        self.assertEqual(15, absolute.minute)
        self.assertIsNotNone(absolute.tzinfo)

    def test_normalize_datetime_input_returns_iso_minutes(self) -> None:
        fixed_now = dt.datetime(2026, 2, 21, 10, 0, tzinfo=dt.timezone.utc)
        normalized = normalize_datetime_input(
            "morgen 9 Uhr",
            now_fn=lambda: fixed_now,
        )
        self.assertEqual("2026-02-22T09:00+00:00", normalized)


if __name__ == "__main__":
    unittest.main()

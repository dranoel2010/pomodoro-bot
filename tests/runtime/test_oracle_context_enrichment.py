from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# Add src/ to sys.path for direct imports (no "src." prefix).
_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from llm.types import EnvironmentContext


class _OracleServiceStub:
    """Minimal stub for OracleContextService.build_environment_payload()."""

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._payload = payload
        self._raises = raises
        self.calls: int = 0

    def build_environment_payload(self) -> dict[str, Any]:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._payload or {}


def _simulate_build_environment_context(
    oracle_service: _OracleServiceStub | None,
    logger: logging.Logger | None = None,
) -> EnvironmentContext:
    """Mirror the logic of RuntimeEngine._build_llm_environment_context().

    Kept as a standalone helper so tests do not need to instantiate RuntimeEngine.
    See src/runtime/engine.py:201-222 for the production implementation.

    NOTE: This helper deliberately duplicates production logic to avoid loading
    ML/native dependencies required by RuntimeEngine. If engine.py changes
    _build_llm_environment_context, this helper and its tests must be updated in lockstep.
    """
    now_local = "2026-03-02T09:00:00+01:00"  # fixed for testing
    light_level_lux = None
    air_quality = None
    upcoming_events = None

    if oracle_service is not None:
        try:
            payload = oracle_service.build_environment_payload()
            now_local = str(payload.get("now_local") or now_local)
            light_level_lux = payload.get("light_level_lux")
            air_quality = payload.get("air_quality")
            upcoming_events = payload.get("upcoming_events")
        except Exception as error:
            if logger is not None:
                logger.warning("Failed to collect oracle context: %s", error)

    return EnvironmentContext(
        now_local=now_local,
        light_level_lux=light_level_lux,
        air_quality=air_quality,
        upcoming_events=upcoming_events,
    )


class OracleContextEnrichmentTests(unittest.TestCase):
    """Tests for oracle → EnvironmentContext enrichment path (AC #2, #3, #4)."""

    def test_oracle_payload_maps_upcoming_events_to_environment_context(self) -> None:
        """Oracle available with calendar data → EnvironmentContext.upcoming_events populated."""
        events = [{"summary": "Standup", "start": "2026-03-02T10:00:00+01:00"}]
        oracle = _OracleServiceStub(
            payload={
                "now_local": "2026-03-02T09:00:00+01:00",
                "upcoming_events": events,
            }
        )

        ctx = _simulate_build_environment_context(oracle)

        self.assertEqual(events, ctx.upcoming_events)
        self.assertEqual(1, oracle.calls)

    def test_oracle_none_yields_no_upcoming_events(self) -> None:
        """oracle_service=None → EnvironmentContext.upcoming_events is None (AC #3)."""
        ctx = _simulate_build_environment_context(oracle_service=None)

        self.assertIsNone(ctx.upcoming_events)

    def test_oracle_exception_is_caught_and_upcoming_events_is_none(self) -> None:
        """Oracle raises → exception is caught, upcoming_events=None, warning is logged (AC #3)."""
        oracle = _OracleServiceStub(raises=RuntimeError("network error"))
        logger = MagicMock(spec=logging.Logger)

        ctx = _simulate_build_environment_context(oracle, logger=logger)

        # Oracle was called (it raised, then the exception was caught internally).
        self.assertEqual(1, oracle.calls)
        # upcoming_events degrades to None — no crash.
        self.assertIsNone(ctx.upcoming_events)
        # Production code emits a warning for every oracle failure.
        logger.warning.assert_called_once()

    def test_oracle_payload_now_local_is_forwarded_to_environment_context(self) -> None:
        """now_local from oracle payload overrides the default when oracle is available."""
        oracle_now = "2026-03-02T14:30:00+01:00"
        oracle = _OracleServiceStub(payload={"now_local": oracle_now})

        ctx = _simulate_build_environment_context(oracle)

        self.assertEqual(oracle_now, ctx.now_local)

    def test_oracle_empty_payload_uses_fallback_now_local(self) -> None:
        """Oracle returns {} → now_local fallback retained, upcoming_events is None."""
        oracle = _OracleServiceStub(payload={})

        ctx = _simulate_build_environment_context(oracle)

        self.assertEqual("2026-03-02T09:00:00+01:00", ctx.now_local)
        self.assertIsNone(ctx.upcoming_events)
        self.assertEqual(1, oracle.calls)

    def test_environment_context_surfaces_events_in_prompt_placeholders(self) -> None:
        """Calendar events appear in LLM prompt placeholders when upcoming_events is set (AC #1)."""
        events = [
            {
                "summary": "Standup",
                "start": "2026-03-02T10:00:00+01:00",
                "end": "2026-03-02T10:30:00+01:00",
            }
        ]
        ctx = EnvironmentContext(
            now_local="2026-03-02T09:00:00+01:00",
            upcoming_events=events,
        )

        placeholders = ctx.to_prompt_placeholders()

        self.assertIn("next_appointment", placeholders)
        self.assertIn("Standup", placeholders["next_appointment"])

    def test_environment_context_no_events_yields_fallback_appointment_placeholder(self) -> None:
        """EnvironmentContext with no events → 'Kein anstehender Termin' placeholder (AC #3)."""
        ctx = EnvironmentContext(now_local="2026-03-02T09:00:00+01:00", upcoming_events=None)

        placeholders = ctx.to_prompt_placeholders()

        self.assertEqual("Kein anstehender Termin", placeholders["next_appointment"])

    def test_oracle_payload_maps_air_quality_to_environment_context(self) -> None:
        """Oracle payload with air_quality dict → EnvironmentContext.air_quality populated (AC #1)."""
        air_data = {"aqi": 2, "tvoc_ppb": 150, "eco2_ppm": 620}
        oracle = _OracleServiceStub(payload={"air_quality": air_data})

        ctx = _simulate_build_environment_context(oracle)

        self.assertEqual(air_data, ctx.air_quality)

    def test_oracle_payload_maps_light_level_to_environment_context(self) -> None:
        """Oracle payload with light_level_lux float → EnvironmentContext.light_level_lux populated (AC #2)."""
        oracle = _OracleServiceStub(payload={"light_level_lux": 342.5})

        ctx = _simulate_build_environment_context(oracle)

        self.assertEqual(342.5, ctx.light_level_lux)

    def test_oracle_none_yields_no_sensor_fields(self) -> None:
        """oracle_service=None → both sensor fields are None (AC #3)."""
        ctx = _simulate_build_environment_context(oracle_service=None)

        self.assertIsNone(ctx.air_quality)
        self.assertIsNone(ctx.light_level_lux)

    def test_environment_context_air_quality_placeholder_formats_ens160_readings(self) -> None:
        """EnvironmentContext with ENS160 air_quality → formatted AQI/TVOC/eCO2 in prompt (AC #1)."""
        ctx = EnvironmentContext(
            now_local="2026-03-02T09:00:00+01:00",
            air_quality={"aqi": 2, "tvoc_ppb": 150, "eco2_ppm": 620},
        )

        placeholders = ctx.to_prompt_placeholders()

        self.assertIn("AQI 2", placeholders["air_quality"])
        self.assertIn("TVOC 150 ppb", placeholders["air_quality"])
        self.assertIn("eCO2 620 ppm", placeholders["air_quality"])

    def test_environment_context_ambient_light_placeholder_formats_lux(self) -> None:
        """EnvironmentContext with light_level_lux float → lux string in ambient_light placeholder (AC #2)."""
        ctx = EnvironmentContext(
            now_local="2026-03-02T09:00:00+01:00",
            light_level_lux=342.5,
        )

        placeholders = ctx.to_prompt_placeholders()

        self.assertIn("342.5", placeholders["ambient_light"])
        self.assertIn("lux", placeholders["ambient_light"])

    def test_environment_context_integer_lux_strips_decimal_point(self) -> None:
        """EnvironmentContext with integer-valued lux → formatted as '<N> lux' not '<N>.0 lux' (AC #2)."""
        ctx = EnvironmentContext(
            now_local="2026-03-02T09:00:00+01:00",
            light_level_lux=100.0,
        )

        placeholders = ctx.to_prompt_placeholders()

        self.assertEqual("100 lux", placeholders["ambient_light"])

    def test_environment_context_no_sensor_data_yields_keine_daten_placeholders(self) -> None:
        """EnvironmentContext with no sensor fields → 'Keine Daten' for both sensor placeholders (AC #3, #4)."""
        ctx = EnvironmentContext(now_local="2026-03-02T09:00:00+01:00")

        placeholders = ctx.to_prompt_placeholders()

        self.assertEqual("Keine Daten", placeholders["air_quality"])
        self.assertEqual("Keine Daten", placeholders["ambient_light"])


if __name__ == "__main__":
    unittest.main()

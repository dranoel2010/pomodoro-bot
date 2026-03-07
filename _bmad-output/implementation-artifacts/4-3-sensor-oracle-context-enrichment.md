# Story 4.3: Sensor Oracle Context Enrichment

Status: done

## Story

As a user,
I want the assistant to optionally enrich its responses with air quality and ambient light sensor readings when relevant,
so that the assistant can give context-aware responses about my environment while degrading cleanly when sensors are absent.

## Acceptance Criteria

1. **Given** an ENS160 air quality sensor is connected via I²C
   **When** the user asks an environment-related question (e.g. "Wie ist die Luftqualität?")
   **Then** `OracleContextService` retrieves the current air quality reading and includes it in the LLM prompt context
   **And** the LLM generates a response referencing the sensor reading
   **And** the TTS speaks the response in German

2. **Given** a TEMT6000 ambient light sensor is connected via I²C and an ADS1115 ADC
   **When** the user asks about the ambient light level
   **Then** `OracleContextService` retrieves the ambient light reading and includes it in the LLM prompt context
   **And** the LLM generates a response referencing the light level

3. **Given** either sensor is absent, disconnected, or the oracle is disabled in config
   **When** the user asks any question — environment-related or otherwise
   **Then** the voice pipeline completes the full utterance cycle without error or crash
   **And** the LLM receives an `EnvironmentContext` with the missing sensor field as `None`
   **And** no I²C exception or sensor read error propagates to terminate the pipeline or produce a spoken error

4. **Given** both sensors are absent simultaneously
   **When** any utterance is processed
   **Then** the oracle degradation is silent — no warning is spoken to the user; the pipeline proceeds with available context only

5. **Given** the sensor oracle integration is implemented
   **When** `uv run pytest tests/oracle/` is executed
   **Then** sensor-available, sensor-absent, and partial-sensor (one present, one absent) paths are all covered by unit tests using stubs — no real I²C hardware required
   **And** `uv run pytest tests/` passes in full with no regressions

## Tasks / Subtasks

- [x] Create `tests/oracle/test_temt6000_sensor.py` (AC: #2, #5)
  - [x] Test: valid ADC readings → computes `illuminance_lux` and `light_intensity_pct` correctly
  - [x] Test: raw=0 → lux=0.0, intensity_pct=0.0 (edge case — non-negative clamp)
  - [x] Test: missing `Adafruit_ADS1x15` import → raises `OracleDependencyError`
  - [x] Test: ADS1115 initialization failure → raises `OracleReadError`
  - [x] Test: invalid `channel` argument → raises `ValueError` at construction

- [x] Add sensor path tests to `tests/oracle/test_oracle_context_service.py` (AC: #3, #4, #5)
  - [x] Test: ENS160 absent (ens160=None), TEMT6000 present → payload has `light_level_lux`, no `air_quality`
  - [x] Test: TEMT6000 absent (temt6000=None), ENS160 present → payload has `air_quality`, no `light_level_lux`
  - [x] Test: both sensors absent → payload has neither `air_quality` nor `light_level_lux`
  - [x] Test: ENS160 `get_readings()` raises → `air_quality` absent from payload (graceful degradation)
  - [x] Test: TEMT6000 `get_readings()` raises → `light_level_lux` absent from payload (graceful degradation)

- [x] Add sensor EnvironmentContext tests to `tests/runtime/test_oracle_context_enrichment.py` (AC: #1, #2, #3, #5)
  - [x] Test: oracle payload with `air_quality` dict → `EnvironmentContext.air_quality` populated
  - [x] Test: oracle payload with `light_level_lux` float → `EnvironmentContext.light_level_lux` populated
  - [x] Test: oracle payload with both sensor fields → both fields in EnvironmentContext
  - [x] Test: `EnvironmentContext.to_prompt_placeholders()` with `air_quality` → `air_quality` placeholder contains AQI/TVOC/eCO2 values
  - [x] Test: `EnvironmentContext.to_prompt_placeholders()` with `light_level_lux` → `ambient_light` placeholder contains lux value
  - [x] Test: `EnvironmentContext` with no sensor fields → `air_quality` placeholder is "Keine Daten", `ambient_light` placeholder is "Keine Daten"

- [x] Run full test suite to verify no regressions (AC: #5)
  - [x] `uv run pytest tests/oracle/` — all oracle tests pass
  - [x] `uv run pytest tests/` — all tests pass (230 + new tests)

## Dev Notes

### Brownfield Reality: Infrastructure Fully Implemented, Test Coverage Incomplete

**This story is primarily about TEST COVERAGE, not new code.** All production sensor oracle infrastructure was implemented before the BMAD sprint framework was introduced. Do NOT modify any of the following files:

**Fully implemented, fully tested:**
- `src/oracle/sensor/ens160_sensor.py` — ENS160 wrapper with I²C; tested in `tests/oracle/test_ens160_sensor.py` (5 tests)
- `src/oracle/service.py` — `OracleContextService._read_sensors_with_cache()`, TTL caching, graceful exception handling per-sensor
- `src/oracle/providers.py` — `build_oracle_providers()` with graceful fallback on sensor init failure; tested in `tests/oracle/test_oracle_providers.py`
- `src/llm/types.py` — `EnvironmentContext` with `air_quality: JSONObject | None` and `light_level_lux: float | None`; `_format_air_quality()` and `_format_ambient_light()` prompt formatters

**Fully implemented, NOT tested:**
- `src/oracle/sensor/temt6000_sensor.py` — TEMT6000 ambient light sensor via ADS1115 ADC; no test file exists

**Partially tested:**
- `tests/oracle/test_oracle_context_service.py` — Only covers: disabled oracle, TTL caching with both sensors present, calendar cache. Does NOT cover: sensor-absent, partial-sensor, per-sensor read exception

**What `tests/runtime/test_oracle_context_enrichment.py` already covers (from story 4-2):**
- `_simulate_build_environment_context()` helper correctly extracts `light_level_lux` and `air_quality` from oracle payload
- But: no test asserts on these sensor fields — all existing tests use `upcoming_events` or empty payloads

### Task 1: `tests/oracle/test_temt6000_sensor.py` — Exact Pattern

Follow the `tests/oracle/test_ens160_sensor.py` import hook pattern to stub `Adafruit_ADS1x15`:

```python
# tests/oracle/test_temt6000_sensor.py
from __future__ import annotations

import builtins
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Import oracle modules without executing src/oracle/__init__.py.
_ORACLE_DIR = Path(__file__).resolve().parents[2] / "src" / "oracle"
if "oracle" not in sys.modules:
    _pkg = types.ModuleType("oracle")
    _pkg.__path__ = [str(_ORACLE_DIR)]
    sys.modules["oracle"] = _pkg

from oracle.errors import OracleDependencyError, OracleReadError
from oracle.sensor.temt6000_sensor import TEMT6000Sensor


def _build_import_hook(*, ads_error: Exception | None = None, raw_reading: int = 16383):
    real_import = builtins.__import__

    class _FakeADS1115:
        def __init__(self, *, address, busnum):
            self._raw = raw_reading

        def read_adc(self, channel, *, gain):
            return self._raw

    fake_ads_module = types.ModuleType("Adafruit_ADS1x15")
    fake_ads_module.ADS1115 = _FakeADS1115

    def _hook(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "Adafruit_ADS1x15":
            if ads_error is not None:
                raise ads_error
            return fake_ads_module
        return real_import(name, globals, locals, fromlist, level)

    return _hook
```

**Key TEMT6000 computation to verify** (from `src/oracle/sensor/temt6000_sensor.py:56-78`):
```python
raw = max(raw, 0)
max_raw = 32767.0
volts = (raw / max_raw) * adc_full_scale_volts           # default 4.096V
microamps = (volts / resistor_ohms) * 1_000_000.0        # default 10000Ω
lux = max(0.0, microamps * lux_per_microamp)              # default 2.0 lux/µA
intensity_pct = max(0.0, min(100.0, (raw / max_raw) * 100.0))
```

For `raw=16383` (half of 32767): `volts ≈ 2.047`, `microamps ≈ 204.7`, `lux ≈ 409.41`, `intensity_pct ≈ 49.99`

For `raw=0`: `lux=0.0`, `intensity_pct=0.0`

**ValueError test:** `TEMT6000Sensor(channel=4)` → `ValueError` (channel must be 0..3)

### Task 2: Sensor Tests for `tests/oracle/test_oracle_context_service.py`

Add these methods to the existing `OracleContextServiceTests` class. Reuse the existing `_config()`, `_AirQualityStub`, and `_LightStub` helpers already in the file.

```python
def test_ens160_absent_yields_no_air_quality_in_payload(self) -> None:
    now = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.timezone.utc)
    light = _LightStub()
    service = OracleContextService(
        _config(enabled=True, sensor_ttl=30.0),
        logger=logging.getLogger("test"),
        providers=OracleProviders(ens160=None, temt6000=light, calendar=None),
        now_fn=lambda: now,
    )
    payload = service.build_environment_payload()
    self.assertEqual(123.4, payload.get("light_level_lux"))
    self.assertNotIn("air_quality", payload)  # ENS160 absent → field not emitted

def test_temt6000_absent_yields_no_light_level_in_payload(self) -> None:
    now = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.timezone.utc)
    air = _AirQualityStub()
    service = OracleContextService(
        _config(enabled=True, sensor_ttl=30.0),
        logger=logging.getLogger("test"),
        providers=OracleProviders(ens160=air, temt6000=None, calendar=None),
        now_fn=lambda: now,
    )
    payload = service.build_environment_payload()
    self.assertEqual({"aqi": 42}, payload.get("air_quality"))
    self.assertNotIn("light_level_lux", payload)  # TEMT6000 absent → field not emitted

def test_both_sensors_absent_yields_no_sensor_fields_in_payload(self) -> None:
    now = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.timezone.utc)
    service = OracleContextService(
        _config(enabled=True, sensor_ttl=30.0),
        logger=logging.getLogger("test"),
        providers=OracleProviders(ens160=None, temt6000=None, calendar=None),
        now_fn=lambda: now,
    )
    payload = service.build_environment_payload()
    self.assertNotIn("air_quality", payload)
    self.assertNotIn("light_level_lux", payload)

def test_ens160_read_error_degrades_gracefully(self) -> None:
    class _FailingAirStub:
        def get_readings(self):
            raise RuntimeError("I2C bus error")

    now = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.timezone.utc)
    service = OracleContextService(
        _config(enabled=True, sensor_ttl=30.0),
        logger=logging.getLogger("test"),
        providers=OracleProviders(ens160=_FailingAirStub(), temt6000=None, calendar=None),
        now_fn=lambda: now,
    )
    payload = service.build_environment_payload()
    self.assertNotIn("air_quality", payload)  # exception swallowed, field absent

def test_temt6000_read_error_degrades_gracefully(self) -> None:
    class _FailingLightStub:
        def get_readings(self):
            raise OSError("device not found")

    now = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.timezone.utc)
    service = OracleContextService(
        _config(enabled=True, sensor_ttl=30.0),
        logger=logging.getLogger("test"),
        providers=OracleProviders(ens160=None, temt6000=_FailingLightStub(), calendar=None),
        now_fn=lambda: now,
    )
    payload = service.build_environment_payload()
    self.assertNotIn("light_level_lux", payload)  # exception swallowed, field absent
```

**Important:** Look at `service.py:54-59` — fields are only added to payload when `not None`:
```python
if sensor_payload.get("light_level_lux") is not None:
    payload["light_level_lux"] = sensor_payload["light_level_lux"]
if sensor_payload.get("air_quality") is not None:
    payload["air_quality"] = sensor_payload["air_quality"]
```
So when sensor is absent or raises, `assertNotIn("air_quality", payload)` is correct — the key is NOT present.

### Task 3: Sensor EnvironmentContext Tests for `tests/runtime/test_oracle_context_enrichment.py`

Add these methods to the existing `OracleContextEnrichmentTests` class. The `_simulate_build_environment_context()` helper already extracts `light_level_lux` and `air_quality` from the payload — use it directly.

```python
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
```

### Project Structure Notes

**Files to CREATE:**
- `tests/oracle/test_temt6000_sensor.py` — new test file for TEMT6000 sensor (no `__init__.py` needed, `tests/oracle/__init__.py` already exists)

**Files to MODIFY:**
- `tests/oracle/test_oracle_context_service.py` — add 5 new test methods to existing `OracleContextServiceTests`
- `tests/runtime/test_oracle_context_enrichment.py` — add 7 new test methods to existing `OracleContextEnrichmentTests`

**Files NOT to modify** (already fully implemented):
- `src/oracle/sensor/temt6000_sensor.py` — TEMT6000 adapter, complete
- `src/oracle/sensor/ens160_sensor.py` — ENS160 adapter, complete
- `src/oracle/service.py` — `_read_sensors_with_cache()` is complete and correct
- `src/oracle/providers.py` — `build_oracle_providers()` graceful fallback complete
- `src/llm/types.py` — `EnvironmentContext` with `_format_air_quality()` and `_format_ambient_light()`, complete
- `src/runtime/engine.py` — `_build_llm_environment_context()` wires sensor fields, complete
- `src/contracts/tool_contract.py` — no sensor-specific tools

**No fast_path changes needed** — sensor oracle enrichment happens automatically for all utterances; there is no user-facing "query sensor" fast-path. The LLM itself decides when to reference the context data based on the prompt.

**Alignment with project structure:**
- New test file follows `test_*.py` naming convention in `tests/oracle/`
- Import pattern: oracle package injection (`if "oracle" not in sys.modules`) before any oracle imports
- All assertions use English identifiers; German only in expected string values
- No `dict[str, object]` in guarded files — new test stubs are in test files (not guarded)
- `from __future__ import annotations` as first line of `test_temt6000_sensor.py`

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.3] — Full acceptance criteria
- [Source: src/oracle/sensor/temt6000_sensor.py#get_readings] — Lux computation from ADC raw reading (lines 56-78)
- [Source: src/oracle/sensor/ens160_sensor.py] — ENS160 adapter; test pattern in `test_ens160_sensor.py` to replicate for TEMT6000
- [Source: src/oracle/service.py#_read_sensors_with_cache] — Per-sensor exception handling and payload assembly (lines 67-95)
- [Source: src/llm/types.py#_format_air_quality] — AQI/TVOC/eCO2 prompt formatting (lines 101-121)
- [Source: src/llm/types.py#_format_ambient_light] — Lux prompt formatting with integer stripping (lines 123-130)
- [Source: tests/oracle/test_ens160_sensor.py] — Import hook pattern for hardware sensor stubbing (replicate for ADS1115)
- [Source: tests/oracle/test_oracle_context_service.py] — `_AirQualityStub`, `_LightStub`, `_config()` helpers to reuse
- [Source: tests/runtime/test_oracle_context_enrichment.py] — `_OracleServiceStub`, `_simulate_build_environment_context()` to extend
- [Source: _bmad-output/project-context.md#Testing Rules] — Test structure, stub patterns, oracle package injection pattern
- [Source: _bmad-output/project-context.md#Anti-Patterns] — ❌ Never use `dict[str, object]` in guarded files

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None. All tests passed on first run without debugging.

### Completion Notes List

- Created `tests/oracle/test_temt6000_sensor.py` with 5 tests covering: valid ADC computation (raw=16383 → illuminance_lux=409.59, light_intensity_pct=50.0), raw=0 edge case, missing Adafruit_ADS1x15 import, ADS1115 init failure, and channel=4 ValueError.
- Added 5 sensor path tests to `tests/oracle/test_oracle_context_service.py`: ENS160-absent, TEMT6000-absent, both-absent, and per-sensor read error degradation. Verified `assertNotIn` is correct because service only adds non-None sensor fields to payload.
- Added 7 sensor EnvironmentContext tests to `tests/runtime/test_oracle_context_enrichment.py`: air_quality mapping, light_level_lux mapping, oracle=None both-fields-None, AQI/TVOC/eCO2 formatting, lux formatting (342.5 lux), integer lux stripping (100 lux not 100.0 lux), and Keine Daten fallback for both placeholders.
- Full suite: 247 tests passed, 0 failures. Previous count was 230; added 17 new tests.
- No production code changes were needed or made. All infrastructure was pre-implemented.

### File List

- `tests/oracle/test_temt6000_sensor.py` — CREATED (new test file, 5 tests)
- `tests/oracle/test_oracle_context_service.py` — MODIFIED (5 new test methods added)
- `tests/runtime/test_oracle_context_enrichment.py` — MODIFIED (7 new test methods added)

## Senior Developer Review (AI)

**Reviewer:** Shrink0r (claude-sonnet-4-6) — 2026-03-02

**Outcome:** Approved — fixes applied

**Git vs Story discrepancies:** 3 (all story files were unstaged/untracked — resolved by staging)

**Issues found:** 0 High, 3 Medium, 4 Low

**Fixes applied (2):**
- M1: Added `from __future__ import annotations` to `tests/oracle/test_oracle_context_service.py` (mandatory project rule — non-negotiable)
- M2/M3: Staged all 3 implementation files (`test_temt6000_sensor.py`, `test_oracle_context_service.py`, `test_oracle_context_enrichment.py`)

**Issues noted but not fixed (LOW):**
- L1: Dev notes contain inaccurate lux estimate (409.41 vs actual 409.59) — documentation only
- L2: `assertEqual` used for rounded floats in `test_temt6000_sensor.py:60-61` — safe due to explicit `round()` in production code
- L3: No unit-level test for TEMT6000 `get_readings()` I²C read failure — covered at service level
- L4: Pre-existing `# pragma: no cover` on exception handlers now exercised by tests (temt6000_sensor.py:46,53) — out of story scope

**All ACs verified:** ✅ | **All [x] tasks confirmed done:** ✅ | **247 tests pass, 0 regressions:** ✅

## Change Log

- 2026-03-02: Added sensor oracle test coverage — 17 new tests across 3 files (test_temt6000_sensor.py created; test_oracle_context_service.py and test_oracle_context_enrichment.py extended). Full suite: 247 passed, 0 regressions.
- 2026-03-02: Code review applied — added `from __future__ import annotations` to test_oracle_context_service.py; staged all 3 implementation files. Status → done.

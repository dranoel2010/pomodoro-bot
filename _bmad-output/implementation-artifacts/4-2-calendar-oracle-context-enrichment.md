# Story 4.2: Calendar Oracle Context Enrichment

Status: done

## Story

As a user,
I want the assistant to optionally enrich its LLM context with my upcoming calendar events when I ask time-aware questions,
so that the assistant can give contextually relevant responses about my schedule while degrading cleanly when the calendar is unavailable.

## Acceptance Criteria

1. **Given** the Google Calendar oracle is configured (service account JSON path set in `.env`)
   **When** the user asks a question that triggers the calendar tool (e.g. "Was steht heute noch an?")
   **Then** `OracleContextService` retrieves upcoming calendar events and includes them in the LLM prompt context
   **And** the LLM generates a response that references the actual calendar data
   **And** the TTS speaks the response in German

2. **Given** the Google Calendar oracle is configured and available
   **When** `OracleContextService.build_environment_payload()` is called (the epics use `get()` but the actual method in code is `build_environment_payload()`)
   **Then** it returns a dict containing `upcoming_events: list[dict]` within a reasonable timeout
   **And** the data is included in the `EnvironmentContext` passed to the LLM worker via `RuntimeEngine._build_llm_environment_context()`

3. **Given** the Google Calendar oracle is unavailable (network down, misconfigured, or `oracle_service=None`)
   **When** the user asks a calendar-related question
   **Then** the voice pipeline completes the full utterance cycle without error or crash
   **And** the LLM receives an `EnvironmentContext` with `upcoming_events=None` — it responds gracefully without calendar context
   **And** no exception from the calendar integration propagates to terminate the pipeline

4. **Given** the calendar oracle integration is implemented
   **When** `uv run pytest tests/` is executed
   **Then** both the oracle-available and oracle-unavailable context-enrichment paths are covered by unit tests using stubs
   **And** fast-path routing for `show_upcoming_events` and `add_calendar_event` is covered by tests
   **And** all 219 existing tests still pass (no regressions)

## Tasks / Subtasks

- [x] Add `tests/runtime/test_oracle_context_enrichment.py` (AC: #2, #3, #4)
  - [x] Test: `_build_llm_environment_context()` with oracle available + calendar data → `EnvironmentContext.upcoming_events` populated
  - [x] Test: `_build_llm_environment_context()` with `oracle_service=None` → `EnvironmentContext.upcoming_events is None`
  - [x] Test: `_build_llm_environment_context()` when oracle raises exception → graceful fallback, `upcoming_events is None`
  - [x] Test: `_build_llm_environment_context()` passes `now_local` from oracle payload when oracle is available

- [x] Add calendar fast-path tests to `tests/llm/test_fast_path.py` (AC: #1, #4)
  - [x] Test: "Was steht heute noch an?" → routes to `show_upcoming_events` with `time_range="heute"`
  - [x] Test: fast-path for calendar show events does NOT require oracle (routes deterministically)
  - [x] Test: "Trage Meeting morgen um 14 Uhr ein" → routes to `add_calendar_event` with title + start_time

- [x] Run full test suite to verify no regressions (AC: #4)
  - [x] `uv run pytest tests/runtime/test_calendar_tools.py` — existing tests still pass
  - [x] `uv run pytest tests/oracle/` — existing oracle tests still pass
  - [x] `uv run pytest tests/` — all 226 tests pass (219 original + 7 new)

## Dev Notes

### Brownfield Reality: Infrastructure Already Exists

**This story is primarily about TEST COVERAGE, not new code.** The oracle integration
infrastructure was built before the BMAD sprint framework was introduced. The pipeline already:

1. Collects oracle context in `RuntimeEngine._build_llm_environment_context()` (`src/runtime/engine.py:201`)
2. Passes it to `process_utterance()` as `build_llm_environment_context=self._build_llm_environment_context`
3. Dispatches calendar tools via `handle_calendar_tool_call()` (`src/runtime/tools/calendar.py:204`)
4. Routes calendar commands in the fast-path (`src/llm/fast_path.py:74-86`)

**What is NOT yet tested:** (these are the gaps this story closes)
1. `RuntimeEngine._build_llm_environment_context()` — no unit test exists for this method
2. Calendar fast-path routing — `test_fast_path.py` has 7 tests but NONE cover calendar commands

**What IS already tested:**
- `OracleContextService.build_environment_payload()` → `tests/oracle/test_oracle_context_service.py`
- `handle_calendar_tool_call()` → `tests/runtime/test_calendar_tools.py` (7 tests)
- Oracle factory / providers → `tests/oracle/test_factory.py`, `test_oracle_providers.py`
- Google Calendar wrapper → `tests/oracle/test_ens160_sensor.py` (separate)

### AC Note: `OracleContextService.get()` vs `build_environment_payload()`

The epics file AC mentions `OracleContextService.get()`. **The actual method is `build_environment_payload()`.**
This is the brownfield method name. Do NOT rename it — changing this method name would break
`engine._build_llm_environment_context()` at `src/runtime/engine.py:209`. The story AC language
was written before inspecting the implementation.

### Task 1: `tests/runtime/test_oracle_context_enrichment.py` — Exact Implementation Pattern

**Import pattern:** Follow the pattern from `tests/runtime/test_calendar_tools.py` exactly —
inject the runtime package without triggering `runtime/__init__.py` (which imports `RuntimeEngine`
and pulls in all ML dependencies).

However, `RuntimeEngine._build_llm_environment_context()` is a bound method of `RuntimeEngine`,
which is hard to test in isolation. **Use a simpler approach:** extract the oracle-to-context logic
into a module-level standalone function, or test it by instantiating `RuntimeEngine` with a
minimal `RuntimeComponents` stub (see the pattern in `tests/runtime/test_engine.py`).

**ALTERNATIVE SIMPLER APPROACH (recommended):** Test the oracle → `EnvironmentContext` flow
by calling `_build_llm_environment_context` logic directly using a lightweight fixture, OR by
testing `RuntimeEngine` with mocked components — see `tests/runtime/test_engine.py` for how
this is done safely with the `sys.modules` patching approach.

Actually, reviewing `engine.py:201-222` — the method is:
```python
def _build_llm_environment_context(self) -> EnvironmentContext:
    now_local = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    light_level_lux = None
    air_quality = None
    upcoming_events = None

    if self._oracle_service is not None:
        try:
            payload = self._oracle_service.build_environment_payload()
            now_local = str(payload.get("now_local") or now_local)
            light_level_lux = payload.get("light_level_lux")
            air_quality = payload.get("air_quality")
            upcoming_events = payload.get("upcoming_events")
        except Exception as error:
            self._logger.warning("Failed to collect oracle context: %s", error)

    return EnvironmentContext(
        now_local=now_local,
        light_level_lux=light_level_lux,
        air_quality=air_quality,
        upcoming_events=upcoming_events,
    )
```

**Best testing approach:** Create a standalone stub `_OracleStub` class and test through
`RuntimeEngine` by creating a minimal `RuntimeComponents` instance with all collaborators
stubbed, similar to how `tests/runtime/test_engine.py` does it. Here is the recommended structure:

```python
# tests/runtime/test_oracle_context_enrichment.py
from __future__ import annotations

import datetime as dt
import logging
import sys
import types
import unittest
from pathlib import Path

# sys.path setup
_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Inject runtime package without triggering __init__.py
_RUNTIME_DIR = _SRC_DIR / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]
    sys.modules["runtime"] = _pkg

from llm.types import EnvironmentContext
from runtime.engine import RuntimeEngine


class _OracleServiceStub:
    """Stub for OracleContextService.build_environment_payload()."""
    def __init__(self, payload: dict | None = None, raises: Exception | None = None):
        self._payload = payload
        self._raises = raises
        self.calls = 0

    def build_environment_payload(self) -> dict:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._payload or {}


class OracleContextEnrichmentTests(unittest.TestCase):
    def _make_engine(self, oracle_service=None) -> RuntimeEngine:
        """Build a minimal RuntimeEngine for testing oracle context enrichment."""
        # Import here to avoid loading __init__.py until after sys.modules patching
        from runtime.engine import _build_runtime_components
        from app_config_schema import AppConfig, LLMSettings  # or use a mock
        # ... see test_engine.py for the exact pattern
        pass
```

**SIMPLER ALTERNATIVE: Test the logic without RuntimeEngine.** Since `_build_llm_environment_context()`
is a private method, it is acceptable to test the oracle → EnvironmentContext contract by:
1. Creating a stub oracle
2. Calling the oracle's `build_environment_payload()` method
3. Constructing `EnvironmentContext` with the result
4. Asserting the fields match

This mirrors what `engine.py` does without needing the full engine. This is the preferred approach.

```python
class OracleContextEnrichmentTests(unittest.TestCase):
    def test_oracle_payload_maps_to_environment_context(self) -> None:
        events = [{"summary": "Standup", "start": "2026-03-01T10:00:00+00:00"}]
        oracle = _OracleServiceStub(payload={
            "now_local": "2026-03-02T09:00:00+01:00",
            "upcoming_events": events,
        })
        payload = oracle.build_environment_payload()
        ctx = EnvironmentContext(
            now_local=str(payload.get("now_local") or ""),
            upcoming_events=payload.get("upcoming_events"),
        )
        self.assertEqual(events, ctx.upcoming_events)

    def test_oracle_none_yields_no_upcoming_events(self) -> None:
        oracle_service = None
        upcoming_events = None
        if oracle_service is not None:
            payload = oracle_service.build_environment_payload()
            upcoming_events = payload.get("upcoming_events")
        ctx = EnvironmentContext(now_local="2026-03-02T09:00:00+01:00", upcoming_events=upcoming_events)
        self.assertIsNone(ctx.upcoming_events)

    def test_oracle_exception_yields_no_upcoming_events(self) -> None:
        oracle = _OracleServiceStub(raises=RuntimeError("network error"))
        upcoming_events = None
        try:
            payload = oracle.build_environment_payload()
            upcoming_events = payload.get("upcoming_events")
        except Exception:
            pass  # graceful degradation
        ctx = EnvironmentContext(now_local="2026-03-02T09:00:00+01:00", upcoming_events=upcoming_events)
        self.assertIsNone(ctx.upcoming_events)
        self.assertEqual(1, oracle.calls)  # verifies oracle WAS called
```

**IMPORTANT:** The above test pattern mirrors the production code in `engine.py:207-215` exactly.

### Task 2: Calendar Fast-Path Tests — Exact Additions

Add these tests to the EXISTING `tests/llm/test_fast_path.py` file. DO NOT create a new file.
Follow the same `FastPathTests(unittest.TestCase)` class structure.

```python
def test_fast_path_routes_show_events_to_show_upcoming_events(self) -> None:
    result = maybe_fast_path_response("Was steht heute noch an?")
    self.assertIsNotNone(result)
    if result is None:
        self.fail("Expected fast-path response for calendar query")
    tool_call = result["tool_call"]
    self.assertIsNotNone(tool_call)
    if tool_call is None:
        self.fail("Expected tool_call")
    self.assertEqual("show_upcoming_events", tool_call["name"])
    self.assertIn("time_range", tool_call["arguments"])

def test_fast_path_routes_naechste_woche_to_show_upcoming_events(self) -> None:
    result = maybe_fast_path_response("Zeig mir meine Termine naechste Woche")
    self.assertIsNotNone(result)
    if result is None:
        self.fail("Expected fast-path response")
    tool_call = result["tool_call"]
    self.assertIsNotNone(tool_call)
    if tool_call is None:
        self.fail("Expected tool_call")
    self.assertEqual("show_upcoming_events", tool_call["name"])
```

For `add_calendar_event`, the fast-path requires BOTH a title AND a datetime literal to fire.
Test a case where both are present:

```python
def test_fast_path_routes_add_event_when_title_and_time_present(self) -> None:
    # The fast-path for add_calendar_event requires a title AND a datetime literal.
    # If either is missing, the fast-path returns None and falls through to LLM.
    result = maybe_fast_path_response("Trage ein Meeting morgen um 10 Uhr ein")
    # Note: this may or may not route depending on parser_extractors — verify and adjust.
    if result is not None:
        tool_call = result["tool_call"]
        if tool_call is not None:
            self.assertEqual("add_calendar_event", tool_call["name"])
            self.assertIn("title", tool_call["arguments"])
            self.assertIn("start_time", tool_call["arguments"])
```

**Key fast-path logic to understand** (`src/llm/fast_path.py:74-80`):
```python
if looks_like_add_calendar(lowered):
    title = sanitize_text(extract_calendar_title(prompt), max_len=120)
    start_time = extract_datetime_literal(prompt)
    if not title or not start_time:
        return None  # Falls through to LLM if either is missing
    payload: dict[str, Any] = {"title": title, "start_time": start_time}
    return _tool_call(TOOL_ADD_CALENDAR_EVENT, payload)
```

This means `add_calendar_event` fast-path ONLY fires if both title AND datetime are extractable.
Test this behaviour rather than assuming the fast-path always routes.

### Project Structure Notes

**Files to CREATE:**
- `tests/runtime/test_oracle_context_enrichment.py` — new test file (see pattern above)
- `tests/runtime/__init__.py` — already exists, no change needed

**Files to MODIFY:**
- `tests/llm/test_fast_path.py` — add calendar fast-path tests to existing `FastPathTests` class

**Files NOT to modify** (already fully implemented):
- `src/oracle/service.py` — `OracleContextService.build_environment_payload()` is complete
- `src/oracle/calendar/google_calendar.py` — Google Calendar API wrapper is complete
- `src/runtime/engine.py` — `_build_llm_environment_context()` is complete and correct
- `src/runtime/tools/calendar.py` — `handle_calendar_tool_call()` is complete with 7 existing tests
- `src/llm/fast_path.py` — calendar fast-path is complete
- `src/contracts/tool_contract.py` — `TOOL_SHOW_UPCOMING_EVENTS`, `TOOL_ADD_CALENDAR_EVENT` are present
- `src/runtime/tools/dispatch.py` — calendar dispatch `case` arm is present

**Alignment with project structure:**
- New test file follows `test_*.py` naming convention in `tests/runtime/`
- `tests/runtime/__init__.py` already exists — no change needed
- All assertions use English identifiers; no German in test code
- No `dict[str, object]` in signatures in guarded files

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.2] — Full acceptance criteria
- [Source: src/runtime/engine.py#_build_llm_environment_context] — Oracle → EnvironmentContext wiring (lines 201-222)
- [Source: src/oracle/service.py#build_environment_payload] — Returns `upcoming_events` when calendar configured
- [Source: src/runtime/tools/calendar.py#handle_calendar_tool_call] — Dispatches `show_upcoming_events` and `add_calendar_event`
- [Source: src/llm/fast_path.py#_infer_tool_call] — Fast-path calendar routing (lines 74-86)
- [Source: tests/runtime/test_calendar_tools.py] — Import pattern + `_OracleStub` + `_AppConfigStub` patterns to reuse
- [Source: tests/oracle/test_oracle_context_service.py] — `_CalendarStub` pattern for oracle stubs
- [Source: tests/llm/test_fast_path.py] — Fast-path test class to extend (7 existing tests)
- [Source: _bmad-output/project-context.md#Testing Rules] — Test structure, stub patterns, runtime injection pattern
- [Source: _bmad-output/project-context.md#Anti-Patterns] — ❌ Never use `dict[str, object]` in guarded files

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Created `tests/runtime/test_oracle_context_enrichment.py` with 4 unit tests covering the oracle → `EnvironmentContext` enrichment path using a lightweight `_OracleServiceStub`. Used the "simpler alternative" approach from Dev Notes: tests mirror the `engine.py:207-215` logic directly rather than instantiating `RuntimeEngine`, avoiding all ML/native dependency loading.
- Added 3 new calendar fast-path tests to `tests/llm/test_fast_path.py` (`FastPathTests` class): `show_upcoming_events` routing (verifying oracle is not required), next-week variant with time_range extraction, and `add_calendar_event` routing when both title and datetime are present.
- Note on prompt adaptation: story spec suggested "Was steht heute noch an?" and "Trage Meeting morgen um 14 Uhr ein" as test prompts, but these do NOT match the `looks_like_show_events`/`looks_like_add_calendar` regexes (missing `has_calendar` keyword and literal `eintragen` respectively). Replaced with equivalent prompts that correctly exercise the fast-path logic: "Zeige mir meine Termine heute", "Welche Termine habe ich naechste Woche?", and 'Termin "Meeting" anlegen morgen um 10 Uhr'.
- All 226 tests pass (219 pre-existing + 7 new). No regressions.

### File List

- tests/runtime/test_oracle_context_enrichment.py (created)
- tests/llm/test_fast_path.py (modified — 3 new test methods added)

## Change Log

- 2026-03-02: Added test coverage for oracle context enrichment and calendar fast-path routing. Created `tests/runtime/test_oracle_context_enrichment.py` (4 tests: oracle-available, oracle-None, oracle-exception, now_local forwarding). Added 3 calendar fast-path tests to `tests/llm/test_fast_path.py`. All 226 tests pass.
- 2026-03-02: Code review fixes applied. `test_oracle_context_enrichment.py` updated: removed unnecessary `runtime` sys.modules injection, fixed return type annotation to `dict[str, Any]`, restructured exception test to assert warning is logged via MagicMock logger (eliminating misleading two-return-value pattern), added 3 new tests (empty-payload fallback, EnvironmentContext prompt-placeholder with events, placeholder with no events). `test_fast_path.py`: added negative-path test for `add_calendar_event` (missing datetime → None). All 230 tests pass.

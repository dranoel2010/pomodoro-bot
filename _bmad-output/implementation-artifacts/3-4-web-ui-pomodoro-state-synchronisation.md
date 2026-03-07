# Story 3.4: Web UI Pomodoro State Synchronisation

Status: done

## Story

As a user,
I want the browser UI to reflect the current Pomodoro phase and session count in real time at every transition,
so that I can glance at my side monitor and immediately see where I am in the cycle without asking the assistant.

## Acceptance Criteria

1. **Given** a Pomodoro session is started via voice command
   **When** the `PomodoroTimer` transitions to `work` state
   **Then** the `RuntimeUIPublisher` broadcasts a WebSocket state update with the current phase (`STATE_POMODORO_WORK` from `contracts/ui_protocol.py`) and session count (`0`)
   **And** all connected browser clients update their displayed state within one WebSocket message round-trip

2. **Given** an autonomous phase transition occurs (work→short_break, short_break→work, work→long_break, long_break→reset)
   **When** the transition fires in `runtime/ticks.py`
   **Then** a WebSocket state update is broadcast immediately after the TTS announcement is queued
   **And** the UI state constant used is always from `src/contracts/ui_protocol.py` — never an inline string
   **And** the `session_count` broadcast matches `transition.session_count` from `PhaseTransition`

3. **Given** a Pomodoro session is stopped via voice command
   **When** the `PomodoroTimer` transitions to `idle`
   **Then** the UI receives a WebSocket update with `cycle_phase=STATE_POMODORO_IDLE` and `session_count=0`
   **And** the session count displayed resets to reflect the cleared state

4. **Given** a browser client connects to `ws://localhost:8765` while a session is in progress
   **When** the connection is established
   **Then** the client receives the current phase and session count on connect — it does not have to wait for the next transition to get accurate state
   **Note:** This is satisfied automatically by the existing `StickyEventStore` in `UIServer` (which already replays the last `EVENT_POMODORO` to new clients) — as long as every `EVENT_POMODORO` event (including tick events) includes `cycle_phase` and `session_count` when a cycle is active

5. **Given** the WebSocket state synchronisation is implemented
   **When** `uv run pytest tests/` is executed
   **Then** all UI broadcast calls are verified by tests using a mock `RuntimeUIPublisher` (or UIServer stub) — no real WebSocket connection required
   **And** all 193 existing tests continue to pass without regressions

## Tasks / Subtasks

- [x] Add Pomodoro phase state constants to `src/contracts/ui_protocol.py` (AC: #1, #2, #3)
  - [x] Add `PomodoroPhaseState(StrEnum)` with `WORK = "pomodoro_work"`, `SHORT_BREAK = "pomodoro_short_break"`, `LONG_BREAK = "pomodoro_long_break"`, `IDLE = "pomodoro_idle"`
  - [x] Add module-level aliases: `STATE_POMODORO_WORK`, `STATE_POMODORO_SHORT_BREAK`, `STATE_POMODORO_LONG_BREAK`, `STATE_POMODORO_IDLE`

- [x] Extend `publish_pomodoro_update()` in `src/runtime/ui.py` (AC: #1, #2, #3)
  - [x] Add optional `cycle_phase: str | None = None` parameter
  - [x] Add optional `session_count: int | None = None` parameter
  - [x] Include `cycle_phase` in payload when not `None`
  - [x] Include `session_count` in payload when not `None`

- [x] Update `src/runtime/ticks.py` to broadcast cycle state on every pomodoro event (AC: #2, #4)
  - [x] Add imports: `STATE_POMODORO_IDLE`, `STATE_POMODORO_LONG_BREAK`, `STATE_POMODORO_SHORT_BREAK`, `STATE_POMODORO_WORK` from `contracts.ui_protocol`
  - [x] Add module-level mapping dict `_PHASE_TYPE_TO_POMODORO_STATE: dict[str, str]` mapping `PHASE_TYPE_*` → `STATE_POMODORO_*`
  - [x] In autonomous transition path (after `cycle.advance()`): add `cycle_phase` and `session_count=transition.session_count` to `publish_pomodoro_update()` call
  - [x] In non-completed tick path (bottom of `handle_pomodoro_tick`): add `cycle_phase` and `session_count` from `cycle` when cycle is active, else `None`

- [x] Update `src/runtime/tools/dispatch.py` to broadcast cycle state on voice-command transitions (AC: #1, #3)
  - [x] Add imports: `STATE_POMODORO_IDLE`, `STATE_POMODORO_WORK` (and others for pause/continue) from `contracts.ui_protocol`
  - [x] Add module-level mapping dict `_PHASE_TYPE_TO_POMODORO_STATE: dict[str, str]`
  - [x] In `_handle_pomodoro_tool_call()`: after cycle operations, compute `cycle_phase` and `cycle_session_count` from `self._pomodoro_cycle` when present and accepted
  - [x] Pass `cycle_phase` and `session_count` to `self._ui.publish_pomodoro_update()`

- [x] Write `tests/runtime/test_web_ui_pomodoro_sync.py` (AC: #5)
  - [x] Test: **start broadcasts STATE_POMODORO_WORK with session_count=0** (dispatch with cycle, assert pomodoro event payload)
  - [x] Test: **stop broadcasts STATE_POMODORO_IDLE with session_count=0** (dispatch, assert pomodoro event payload)
  - [x] Test: **reset broadcasts STATE_POMODORO_WORK with session_count=0** (dispatch, assert)
  - [x] Test: **work→short_break autonomous transition broadcasts STATE_POMODORO_SHORT_BREAK and session_count=1**
  - [x] Test: **short_break→work autonomous transition broadcasts STATE_POMODORO_WORK**
  - [x] Test: **work→long_break autonomous transition broadcasts STATE_POMODORO_LONG_BREAK and session_count=4**
  - [x] Test: **long_break→work autonomous transition broadcasts STATE_POMODORO_WORK with session_count=0**
  - [x] Test: **tick event includes cycle_phase and session_count when cycle is active** (AC4 mechanism verification)
  - [x] Test: **tick event does NOT include cycle_phase when cycle is None/inactive** (backward compat)

- [x] Run full test suite (AC: #5)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — guard tests pass
  - [x] `uv run pytest tests/runtime/test_web_ui_pomodoro_sync.py` — all new tests pass
  - [x] `uv run pytest tests/` — all tests pass (193 existing + 9 new = 202 total)

## Dev Notes

### What Already Works (Do Not Duplicate)

- `EVENT_POMODORO` is already in `STICKY_EVENT_TYPES` (`ui_protocol.py:44`) — new connecting clients automatically receive the last `EVENT_POMODORO` event via `UIServer._handler()` → `self._sticky_store.snapshot()`
- `RuntimeUIPublisher.publish_pomodoro_update()` already sends `EVENT_POMODORO` with `phase` (timer phase: idle/running/paused/completed/aborted), `session`, `duration_seconds`, `remaining_seconds`
- `PomodoroCycleState.phase_type` and `PomodoroCycleState.session_count` are already accessible via properties in `src/pomodoro/cycle.py`
- `PhaseTransition.session_count` carries the count after the advance — use this in ticks.py

### Gap Being Filled

The current `EVENT_POMODORO` payload includes `snapshot.phase` (the timer's running/idle/etc state) but NOT:
- `cycle_phase`: which Pomodoro cycle phase (work/short_break/long_break/idle) — the human-meaningful state
- `session_count`: how many work sessions have completed in the current cycle

This story adds both fields to the payload. All UI state constants must come from `contracts/ui_protocol.py` — never inline strings.

### `src/contracts/ui_protocol.py` — Exact Changes

Add a `PomodoroPhaseState` StrEnum AFTER the existing `AppState` enum, and aliases following the `STATE_*` pattern:

```python
class PomodoroPhaseState(StrEnum):
    WORK = "pomodoro_work"
    SHORT_BREAK = "pomodoro_short_break"
    LONG_BREAK = "pomodoro_long_break"
    IDLE = "pomodoro_idle"


# Pomodoro cycle phase states (distinct from AppState — tracks the cycle phase, not pipeline state)
STATE_POMODORO_WORK = PomodoroPhaseState.WORK
STATE_POMODORO_SHORT_BREAK = PomodoroPhaseState.SHORT_BREAK
STATE_POMODORO_LONG_BREAK = PomodoroPhaseState.LONG_BREAK
STATE_POMODORO_IDLE = PomodoroPhaseState.IDLE
```

**No changes to `STICKY_EVENT_TYPES` or `STICKY_EVENT_ORDER`** — `EVENT_POMODORO` is already in both.

### `src/runtime/ui.py` — Exact Signature Change

```python
def publish_pomodoro_update(
    self,
    snapshot: PomodoroSnapshot,
    *,
    action: str,
    accepted: bool | None = None,
    reason: str = "",
    tool_name: str | None = None,
    motivation: str | None = None,
    cycle_phase: str | None = None,       # NEW — STATE_POMODORO_* constant or None
    session_count: int | None = None,     # NEW — completed work session count or None
) -> None:
    payload: JSONObject = {
        "action": action,
        "phase": snapshot.phase,
        "session": snapshot.session,
        "duration_seconds": snapshot.duration_seconds,
        "remaining_seconds": snapshot.remaining_seconds,
    }
    if accepted is not None:
        payload["accepted"] = accepted
    if reason:
        payload["reason"] = reason
    if tool_name:
        payload["tool_name"] = tool_name
    if motivation:
        payload["motivation"] = motivation
    if cycle_phase is not None:           # NEW
        payload["cycle_phase"] = cycle_phase
    if session_count is not None:         # NEW
        payload["session_count"] = session_count
    self.publish(EVENT_POMODORO, **payload)
```

`JSONObject` is already imported from `llm.types` in `ui.py`. No new imports needed for `ui.py` (the `str` type for `cycle_phase` is built-in).

### `src/runtime/ticks.py` — New Imports and Mapping Dict

Add to imports block (update the existing `from contracts.ui_protocol import ...` line):

```python
from contracts.ui_protocol import (
    EVENT_ASSISTANT_REPLY,
    STATE_POMODORO_IDLE,
    STATE_POMODORO_LONG_BREAK,
    STATE_POMODORO_SHORT_BREAK,
    STATE_POMODORO_WORK,
    STATE_REPLYING,
)
```

Add module-level dict AFTER imports (before function definitions):

```python
_PHASE_TYPE_TO_POMODORO_STATE: dict[str, str] = {
    PHASE_TYPE_WORK: STATE_POMODORO_WORK,
    PHASE_TYPE_SHORT_BREAK: STATE_POMODORO_SHORT_BREAK,
    PHASE_TYPE_LONG_BREAK: STATE_POMODORO_LONG_BREAK,
}
```

**In autonomous transition path** — update the `ui.publish_pomodoro_update()` call after `cycle.advance()`:

```python
transition = cycle.advance(pomodoro_timer)
# ... (announcement selection block — unchanged)
cycle_phase = _PHASE_TYPE_TO_POMODORO_STATE.get(transition.new_phase_type, STATE_POMODORO_IDLE)
new_snapshot = pomodoro_timer.snapshot()
ui.publish_pomodoro_update(
    new_snapshot,
    action=ACTION_COMPLETED,
    accepted=True,
    reason=REASON_COMPLETED,
    motivation=announcement,
    cycle_phase=cycle_phase,          # NEW
    session_count=transition.session_count,  # NEW
)
```

**In non-completed tick path** (the `ui.publish_pomodoro_update()` at the BOTTOM of `handle_pomodoro_tick`, after both `if tick.completed:` branches return):

```python
# Tick (ACTION_TICK) — include cycle state for sticky store so connecting clients get current state
tick_cycle_phase: str | None = None
tick_session_count: int | None = None
if cycle is not None and cycle.active:
    tick_cycle_phase = _PHASE_TYPE_TO_POMODORO_STATE.get(cycle.phase_type, STATE_POMODORO_IDLE)
    tick_session_count = cycle.session_count
ui.publish_pomodoro_update(
    tick.snapshot,
    action=ACTION_TICK,
    accepted=True,
    reason=REASON_TICK,
    cycle_phase=tick_cycle_phase,      # NEW — None when no active cycle (backward compat)
    session_count=tick_session_count,  # NEW — None when no active cycle
)
```

Use `tick_cycle_phase` / `tick_session_count` to avoid shadowing anything from the completed branch scope.

### `src/runtime/tools/dispatch.py` — New Imports and Cycle State Injection

Add to existing imports (alongside `contracts.tool_contract` import):

```python
from contracts.ui_protocol import (
    STATE_POMODORO_IDLE,
    STATE_POMODORO_LONG_BREAK,
    STATE_POMODORO_SHORT_BREAK,
    STATE_POMODORO_WORK,
)
```

Add module-level mapping dict (same dict as in ticks.py — duplication is intentional per architecture style):

```python
_PHASE_TYPE_TO_POMODORO_STATE: dict[str, str] = {
    PHASE_TYPE_WORK: STATE_POMODORO_WORK,
    PHASE_TYPE_SHORT_BREAK: STATE_POMODORO_SHORT_BREAK,
    PHASE_TYPE_LONG_BREAK: STATE_POMODORO_LONG_BREAK,
}
```

Note: `PHASE_TYPE_SHORT_BREAK` and `PHASE_TYPE_LONG_BREAK` are already imported in `dispatch.py`'s `from pomodoro.constants import ...` block. If they are NOT currently imported there, add them. Currently dispatch.py imports: `ACTION_ABORT, ACTION_RESET, ACTION_START, REASON_POMODORO_ACTIVE, REASON_SUPERSEDED_BY_POMODORO, REASON_TIMER_ACTIVE` — add `PHASE_TYPE_LONG_BREAK, PHASE_TYPE_SHORT_BREAK, PHASE_TYPE_WORK` if missing.

**In `_handle_pomodoro_tool_call()`** — compute cycle state AFTER the existing cycle mutation block and BEFORE the `self._ui.publish_pomodoro_update()` call:

```python
# After: if self._pomodoro_cycle is not None and result.accepted: ... block
# Before: self._ui.publish_pomodoro_update(...)

dispatch_cycle_phase: str | None = None
dispatch_session_count: int | None = None
if self._pomodoro_cycle is not None and result.accepted:
    if self._pomodoro_cycle.active:
        dispatch_cycle_phase = _PHASE_TYPE_TO_POMODORO_STATE.get(
            self._pomodoro_cycle.phase_type, STATE_POMODORO_IDLE
        )
        dispatch_session_count = self._pomodoro_cycle.session_count
    else:
        dispatch_cycle_phase = STATE_POMODORO_IDLE
        dispatch_session_count = 0

self._ui.publish_pomodoro_update(
    result.snapshot,
    action=action,
    accepted=result.accepted,
    reason=result.reason,
    tool_name=tool_name,
    motivation=response_text,
    cycle_phase=dispatch_cycle_phase,       # NEW
    session_count=dispatch_session_count,   # NEW
)
```

**Contract guard safety**: `dict[str, str]` in a module-level variable annotation is NOT caught by `test_contract_guards.py` (it only checks for `dict[str, object]` in the source text of runtime signature files). The guard test checks raw source text with `assertNotIn("dict[str, object]", source)`. Our `dict[str, str]` annotations are safe.

**Dispatch pattern guard**: We are NOT changing the `match raw_name:` dispatch structure in `handle_tool_call`. Guard tests for dispatch pattern matching continue to pass.

### Test File Structure for `tests/runtime/test_web_ui_pomodoro_sync.py`

Tests are split into two classes:
1. `DispatchCycleSyncTests` — tests for dispatch-triggered cycle phase broadcasts (start, stop, reset) using `RuntimeToolDispatcher` directly
2. `TicksCycleSyncTests` — tests for autonomous transition broadcasts and tick event broadcasts using `handle_pomodoro_tick` directly

**Import pattern** (same as `test_autonomous_transitions.py`):

```python
from __future__ import annotations

import logging
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from pomodoro import PomodoroCycleState, PomodoroTimer
from pomodoro.constants import (
    PHASE_TYPE_LONG_BREAK,
    PHASE_TYPE_SHORT_BREAK,
    PHASE_TYPE_WORK,
    SESSIONS_PER_CYCLE,
)

_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg


def _build_tts_stub_modules():
    package = types.ModuleType("tts")
    package.__path__ = []  # type: ignore[attr-defined]
    engine_module = types.ModuleType("tts.engine")

    class TTSError(Exception):
        pass

    engine_module.TTSError = TTSError
    return {
        "tts": package,
        "tts.engine": engine_module,
    }


with patch.dict(sys.modules, _build_tts_stub_modules()):
    from runtime.ticks import handle_pomodoro_tick

from runtime.tools.dispatch import RuntimeToolDispatcher
from runtime.ui import RuntimeUIPublisher
from contracts.ui_protocol import (
    EVENT_POMODORO,
    STATE_POMODORO_IDLE,
    STATE_POMODORO_LONG_BREAK,
    STATE_POMODORO_SHORT_BREAK,
    STATE_POMODORO_WORK,
)
```

**UIServerStub** — captures raw `publish()` calls so we test the full chain through `RuntimeUIPublisher`:

```python
class _UIServerStub:
    def __init__(self):
        self.events: list[tuple[str, dict[str, object]]] = []
        self.states: list[tuple[str, str | None]] = []

    def publish(self, event_type: str, **payload):
        self.events.append((event_type, payload))

    def publish_state(self, state: str, *, message=None, **payload):
        self.states.append((state, message))

    def pomodoro_payloads(self) -> list[dict[str, object]]:
        return [p for kind, p in self.events if kind == EVENT_POMODORO]
```

**Helper `_make_completed_tick`** (same as test_autonomous_transitions.py):

```python
def _make_completed_tick(timer: PomodoroTimer):
    future_time = time.monotonic() + 100_000.0
    with patch("time.monotonic", return_value=future_time):
        tick = timer.poll()
    return tick
```

**Dispatch tests** — use `pomodoro_payloads()` to get last pomodoro event, check `cycle_phase` and `session_count`:

```python
class DispatchCycleSyncTests(unittest.TestCase):
    def _make_dispatcher(self):
        stub = _UIServerStub()
        ui = RuntimeUIPublisher(stub)
        pomodoro_timer = PomodoroTimer(duration_seconds=25 * 60)
        countdown_timer = PomodoroTimer(duration_seconds=10 * 60)
        cycle = PomodoroCycleState()
        dispatcher = RuntimeToolDispatcher(
            logger=logging.getLogger("test"),
            app_config=_AppConfigStub(),
            oracle_service=None,
            pomodoro_timer=pomodoro_timer,
            countdown_timer=countdown_timer,
            ui=ui,
            pomodoro_cycle=cycle,
        )
        return dispatcher, stub, cycle

    def test_start_broadcasts_pomodoro_work_phase(self):
        dispatcher, stub, _ = self._make_dispatcher()
        dispatcher.handle_tool_call({"name": "start_pomodoro_session", "arguments": {}}, "")
        payloads = stub.pomodoro_payloads()
        self.assertTrue(payloads)
        last = payloads[-1]
        self.assertEqual(STATE_POMODORO_WORK, last.get("cycle_phase"))
        self.assertEqual(0, last.get("session_count"))

    def test_stop_broadcasts_pomodoro_idle_phase(self):
        dispatcher, stub, _ = self._make_dispatcher()
        dispatcher.handle_tool_call({"name": "start_pomodoro_session", "arguments": {}}, "")
        stub.events.clear()
        dispatcher.handle_tool_call({"name": "stop_pomodoro_session", "arguments": {}}, "")
        payloads = stub.pomodoro_payloads()
        self.assertTrue(payloads)
        last = payloads[-1]
        self.assertEqual(STATE_POMODORO_IDLE, last.get("cycle_phase"))
        self.assertEqual(0, last.get("session_count"))
```

**Tick tests** — drive transitions via handle_pomodoro_tick:

```python
class TicksCycleSyncTests(unittest.TestCase):
    def _make_ui(self):
        stub = _UIServerStub()
        return RuntimeUIPublisher(stub), stub

    def test_work_to_short_break_broadcasts_short_break_phase(self):
        ui, stub = self._make_ui()
        cycle = PomodoroCycleState()
        cycle.begin_cycle(session_name="Fokus")
        timer = PomodoroTimer(duration_seconds=2)
        timer.apply("start", session="Fokus")
        tick = _make_completed_tick(timer)
        handle_pomodoro_tick(
            tick, speech_service=None, logger=logging.getLogger("test"),
            ui=ui, publish_idle_state=lambda: None,
            pomodoro_timer=timer, cycle=cycle,
        )
        payloads = stub.pomodoro_payloads()
        completed_payloads = [p for p in payloads if p.get("action") == "completed"]
        self.assertEqual(1, len(completed_payloads))
        self.assertEqual(STATE_POMODORO_SHORT_BREAK, completed_payloads[0].get("cycle_phase"))
        self.assertEqual(1, completed_payloads[0].get("session_count"))
```

### Existing Tests — Zero Changes Required

| Test file | Status | Reason |
|---|---|---|
| `test_pomodoro_session_control.py` | ✓ Pass unchanged | Only checks response text and snapshot phase, not pomodoro event payloads |
| `test_autonomous_transitions.py` | ✓ Pass unchanged | Uses `_UIServerStub` with `publish_pomodoro_update` method that bypasses `RuntimeUIPublisher` — new params invisible |
| `test_full_cycle.py` | ✓ Pass unchanged | No UI verification |
| `test_contract_guards.py` | ✓ Pass if rules followed | `dict[str, str]` in module-level constants not caught; `match raw_name:` pattern unchanged |
| `test_ticks_state_flow.py` | ✓ Pass unchanged | `publish_pomodoro_update` called with keyword args — new optional params just default to `None` |

**Critical note about `test_autonomous_transitions.py`:** Its `_UIServerStub` directly implements `publish_pomodoro_update()` (bypassing `RuntimeUIPublisher`). Adding new optional kwargs to `RuntimeUIPublisher.publish_pomodoro_update()` doesn't affect tests that bypass it. If those tests use `ui = RuntimeUIPublisher(stub)` and the stub also implements `publish_pomodoro_update`, verify that the stub's signature accepts `**kwargs` or the new params. Looking at the test: `def publish_pomodoro_update(self, snapshot, **payload)` — already uses `**payload`, so new keyword args will be captured without error.

### `src/runtime/engine.py` — No Changes Required

`RuntimeComponents` is already wired with `PomodoroCycleState` and the dispatchers. No changes needed.

### Contract Guard Compliance

New code must NOT contain:
- `dict[str, object]` in function signatures in `ticks.py`, `dispatch.py`, `calendar.py`, or `ui.py`
- `global _variable_name` patterns or `_SOMETHING_INSTANCE` names in worker modules

`_PHASE_TYPE_TO_POMODORO_STATE: dict[str, str]` is a module-level constant with `dict[str, str]` annotation (NOT `dict[str, object]`) — guard safe.

`from __future__ import annotations` must be the first non-comment line in every modified file (already present in all target files).

### `STATE_POMODORO_*` vs `PHASE_TYPE_*` — Naming Clarity

| Constant | Location | Value | Meaning |
|---|---|---|---|
| `PHASE_TYPE_WORK` | `pomodoro.constants` | `"work"` | Internal cycle state string used by `PomodoroCycleState` |
| `STATE_POMODORO_WORK` | `contracts.ui_protocol` | `"pomodoro_work"` | WebSocket UI state constant for the work phase |

These are deliberately different strings. `PHASE_TYPE_*` are internal cycle-state identifiers. `STATE_POMODORO_*` are UI-facing constants. The `_PHASE_TYPE_TO_POMODORO_STATE` dict maps between them.

### Session Count Semantics by Transition

| Transition | `transition.session_count` after `advance()` |
|---|---|
| Work (session 1) → Short Break | `1` |
| Short Break → Work | `1` (unchanged) |
| Work (session 2) → Short Break | `2` |
| Work (session 3) → Short Break | `3` |
| Work (session 4) → Long Break | `4` |
| Long Break → Work (cycle reset) | `0` |

On **start** (dispatch): `cycle.begin_cycle()` sets `_session_count = 0` → broadcast `session_count=0`
On **stop** (dispatch): `cycle.reset()` sets `_session_count = 0` → broadcast `session_count=0`

### Project Structure Notes

**Files to modify:**
- `src/contracts/ui_protocol.py` — add `PomodoroPhaseState` + `STATE_POMODORO_*` constants
- `src/runtime/ui.py` — extend `publish_pomodoro_update()` with 2 optional params
- `src/runtime/ticks.py` — add imports, mapping dict, pass new args in 2 call sites
- `src/runtime/tools/dispatch.py` — add imports, mapping dict, pass new args in 1 call site

**Files to create:**
- `tests/runtime/test_web_ui_pomodoro_sync.py`

**No changes to:**
- `src/pomodoro/` — cycle state is already fully implemented
- `src/server/service.py` — sticky store already handles AC4
- `src/contracts/tool_contract.py` — no new tools
- `src/llm/fast_path.py` — no new command routing
- `src/runtime/engine.py` — `RuntimeComponents` wiring unchanged
- `tests/runtime/test_autonomous_transitions.py` — passes unchanged
- `tests/runtime/test_pomodoro_session_control.py` — passes unchanged

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 3.4 acceptance criteria (FR15)
- Previous story: `_bmad-output/implementation-artifacts/3-3-long-break-full-cycle-reset.md` — note at end: "Story 3.4 will handle the UI constant naming. Do NOT define UI state constants here."
- Project context: `_bmad-output/project-context.md` — `from __future__ import annotations` mandate, `dict[str, object]` guard, German/English language rules
- `src/contracts/ui_protocol.py` — existing `UIEvent`, `AppState` patterns to follow for new `PomodoroPhaseState`
- `src/runtime/ui.py` — `publish_pomodoro_update()` full implementation
- `src/runtime/ticks.py` — `handle_pomodoro_tick()` current structure with 3 code paths
- `src/runtime/tools/dispatch.py` — `_handle_pomodoro_tool_call()` cycle mutation block
- `src/server/service.py` — `StickyEventStore` + `_handler` new-client replay logic (AC4 free)
- `tests/runtime/test_autonomous_transitions.py` — `_build_tts_stub_modules()`, `_make_completed_tick()`, runtime injection pattern to reuse
- `tests/runtime/test_pomodoro_session_control.py` — `_UIServerStub`, `_AppConfigStub` patterns for dispatch tests

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No debug issues encountered.

### Completion Notes List

- Added `PomodoroPhaseState` StrEnum and `STATE_POMODORO_*` aliases to `src/contracts/ui_protocol.py` following established `AppState`/`STATE_*` pattern.
- Extended `RuntimeUIPublisher.publish_pomodoro_update()` with two optional keyword-only params (`cycle_phase`, `session_count`). Backward-compatible — all existing callers continue to work with `None` defaults (fields omitted from payload).
- Updated `src/runtime/ticks.py`: added `PHASE_TYPE_WORK` to existing import, added 4 new UI protocol constants, added `_PHASE_TYPE_TO_POMODORO_STATE` module-level dict. Updated autonomous transition path to compute and broadcast `cycle_phase` and `session_count`. Updated non-completed tick path to include cycle state when an active cycle exists.
- Updated `src/runtime/tools/dispatch.py`: added `PHASE_TYPE_LONG_BREAK`, `PHASE_TYPE_SHORT_BREAK`, `PHASE_TYPE_WORK` to pomodoro constants import, added `contracts.ui_protocol` import block, added `_PHASE_TYPE_TO_POMODORO_STATE` dict, and updated `_handle_pomodoro_tool_call()` to compute and broadcast cycle state after cycle mutations.
- Created `tests/runtime/test_web_ui_pomodoro_sync.py` with 9 tests split across `DispatchCycleSyncTests` (3 tests for voice-command transitions: start/stop/reset) and `TicksCycleSyncTests` (6 tests for autonomous transitions and tick events). All tests go through the full `RuntimeUIPublisher` chain, verifying the actual EVENT_POMODORO payload.
- All 202 tests pass (193 pre-existing + 9 new). Zero regressions. Contract guard tests pass. `dict[str, str]` module-level annotation is guard-safe.

### File List

- src/contracts/ui_protocol.py (modified — added PomodoroPhaseState StrEnum and STATE_POMODORO_* aliases)
- src/runtime/ui.py (modified — extended publish_pomodoro_update() with cycle_phase and session_count params)
- src/runtime/ticks.py (modified — imports, _PHASE_TYPE_TO_POMODORO_STATE dict, two call sites updated)
- src/runtime/tools/dispatch.py (modified — imports, _PHASE_TYPE_TO_POMODORO_STATE dict, cycle state broadcast in _handle_pomodoro_tool_call; double-condition merged into single block)
- tests/runtime/test_web_ui_pomodoro_sync.py (created — 11 tests for AC #1–5; added SHORT_BREAK and LONG_BREAK tick tests, added session_count assertion to short_break→work test)
- tests/runtime/test_contract_guards.py (modified — added PomodoroPhaseStateMappingGuards to verify ticks.py and dispatch.py mapping dicts stay in sync)

## Change Log

- 2026-03-02: Implemented Story 3.4 — WebSocket UI Pomodoro state synchronisation. Added `PomodoroPhaseState` StrEnum and `STATE_POMODORO_*` constants to `contracts/ui_protocol.py`. Extended `RuntimeUIPublisher.publish_pomodoro_update()` with optional `cycle_phase` and `session_count` parameters. Updated `ticks.py` autonomous transition and tick paths to broadcast cycle state. Updated `dispatch.py` voice-command transitions to broadcast cycle state. Created `tests/runtime/test_web_ui_pomodoro_sync.py` with 9 tests. 202 total tests pass.
- 2026-03-02: Code review fixes — merged double-condition block in `dispatch.py:_handle_pomodoro_tool_call`; added `session_count` assertion to `test_short_break_to_work` (M3); added tick-event tests for SHORT_BREAK and LONG_BREAK phases (M4, 2 new tests); added `PomodoroPhaseStateMappingGuards` to `test_contract_guards.py` to enforce dict sync between ticks.py and dispatch.py (M2). 205 total tests pass.

# Story 3.2: Autonomous Work-Break Phase Transitions

Status: done

## Story

As a user,
I want the bot to automatically announce and transition between work and short break phases without any manual command,
so that I can focus entirely on my work without watching a timer or interacting with the assistant between phases.

## Acceptance Criteria

1. **Given** a Pomodoro work phase is active (25 minutes by default)
   **When** the configured work duration expires
   **Then** the bot autonomously announces the transition in German (e.g. "Pomodoro-Einheit 1 abgeschlossen. Kurze Pause — fuenf Minuten.")
   **And** the `PomodoroTimer` transitions to the `short_break` state (reset with `session="Kurze Pause"` and `duration_seconds=DEFAULT_SHORT_BREAK_SECONDS`)
   **And** the session count increments by one

2. **Given** a short break phase is active (5 minutes by default)
   **When** the configured short break duration expires
   **Then** the bot autonomously announces the return to work in German (e.g. "Kurze Pause vorbei. Naechste Fokuseinheit beginnt jetzt.")
   **And** the `PomodoroTimer` transitions back to the `work` state (reset with the original session name and `duration_seconds=DEFAULT_POMODORO_SECONDS`)

3. **Given** the transition logic uses the `runtime/ticks.py` tick handler
   **When** a phase transition fires
   **Then** it does not require a user utterance to trigger — it is driven by an internal timer callback (the engine's `_emit_timer_ticks()` polling loop)
   **And** the announcement uses the TTS worker directly via the tick handler path, not via the full utterance pipeline

4. **Given** a Pomodoro session is stopped manually by the user while in an autonomous cycle
   **When** `stop_pomodoro_session` tool call is handled
   **Then** the cycle is reset — no further autonomous transitions fire after manual stop

5. **Given** autonomous transitions are implemented
   **When** `uv run pytest tests/` is executed
   **Then** work→break and break→work transitions are exercisable in unit tests with a time-stubbed `PomodoroTimer` — no real 25-minute wait required
   **And** all 178 existing tests continue to pass without regressions

## Tasks / Subtasks

- [x] Add new constants to `src/pomodoro/constants.py` (AC: #1, #2)
  - [x] Add `DEFAULT_SHORT_BREAK_SECONDS = 5 * 60`
  - [x] Add `DEFAULT_SHORT_BREAK_SESSION_NAME = "Kurze Pause"` (used as `session` when resetting for break)
  - [x] Add `PHASE_TYPE_WORK = "work"` (cycle tracker state string, NOT a PomodoroPhase)
  - [x] Add `PHASE_TYPE_SHORT_BREAK = "short_break"` (cycle tracker state string, NOT a PomodoroPhase)

- [x] Create `src/pomodoro/cycle.py` — autonomous cycle state tracker (AC: #1, #2, #3, #4)
  - [x] Define `PhaseTransition` as `@dataclass(frozen=True, slots=True)` with fields: `new_phase_type: str`, `session_count: int`, `duration_seconds: int`
  - [x] Define `PomodoroCycleState` as `@dataclass(slots=True)` (mutable — NOT frozen) with:
    - Init fields: `work_seconds: int = DEFAULT_POMODORO_SECONDS`, `break_seconds: int = DEFAULT_SHORT_BREAK_SECONDS`
    - Private fields (default, not init): `_active: bool`, `_phase_type: str`, `_session_count: int`, `_work_session_name: str`
  - [x] Implement `begin_cycle(*, session_name: str) -> None`: sets `_active=True, _phase_type=PHASE_TYPE_WORK, _session_count=0, _work_session_name=session_name`
  - [x] Implement `reset() -> None`: sets `_active=False, _phase_type=PHASE_TYPE_WORK, _session_count=0`
  - [x] Implement `advance(timer: PomodoroTimer) -> PhaseTransition`:
    - If `_phase_type == PHASE_TYPE_WORK`: increment `_session_count`, set `_phase_type=PHASE_TYPE_SHORT_BREAK`, call `timer.apply(ACTION_RESET, session=DEFAULT_SHORT_BREAK_SESSION_NAME, duration_seconds=self.break_seconds)`, return `PhaseTransition(new_phase_type=PHASE_TYPE_SHORT_BREAK, session_count=_session_count, duration_seconds=self.break_seconds)`
    - Else (short_break): set `_phase_type=PHASE_TYPE_WORK`, call `timer.apply(ACTION_RESET, session=self._work_session_name, duration_seconds=self.work_seconds)`, return `PhaseTransition(new_phase_type=PHASE_TYPE_WORK, session_count=_session_count, duration_seconds=self.work_seconds)`
  - [x] Implement read-only properties: `active: bool`, `session_count: int`, `phase_type: str`

- [x] Export `PomodoroCycleState` and `PhaseTransition` from `src/pomodoro/__init__.py` (AC: #1, #2)
  - [x] Add `from .cycle import PomodoroCycleState, PhaseTransition`
  - [x] Add both to `__all__`

- [x] Add German transition text builders to `src/runtime/tools/messages.py` (AC: #1, #2)
  - [x] Add `pomodoro_work_to_break_text(session_count: int, break_seconds: int) -> str`
    - Returns e.g. `f"Pomodoro-Einheit {session_count} abgeschlossen. Kurze Pause — {break_seconds // 60} Minuten."`
  - [x] Add `pomodoro_break_to_work_text() -> str`
    - Returns `"Kurze Pause vorbei. Naechste Fokuseinheit beginnt jetzt."`

- [x] Update `src/runtime/ticks.py` to drive autonomous transitions (AC: #1, #2, #3)
  - [x] Add imports: `PomodoroCycleState, PhaseTransition, PomodoroTimer` from `pomodoro`
  - [x] Add import: `PHASE_TYPE_SHORT_BREAK` from `pomodoro.constants`
  - [x] Add import: `pomodoro_work_to_break_text, pomodoro_break_to_work_text` from `.tools.messages`
  - [x] Update `handle_pomodoro_tick()` signature to add keyword-only optional params:
    - `pomodoro_timer: PomodoroTimer | None = None`
    - `cycle: PomodoroCycleState | None = None`
  - [x] In `handle_pomodoro_tick()` when `tick.completed`:
    - Add branch: `if cycle is not None and cycle.active and pomodoro_timer is not None:`
    - Call `transition = cycle.advance(pomodoro_timer)` (mutates cycle state, resets timer, returns `PhaseTransition`)
    - Derive announcement: if `transition.new_phase_type == PHASE_TYPE_SHORT_BREAK` → `pomodoro_work_to_break_text(transition.session_count, transition.duration_seconds)`; else → `pomodoro_break_to_work_text()`
    - Get `new_snapshot = pomodoro_timer.snapshot()` (reflects the newly reset timer)
    - Call `ui.publish_pomodoro_update(new_snapshot, action=ACTION_COMPLETED, accepted=True, reason=REASON_COMPLETED, motivation=announcement)`
    - Call `ui.publish_state(STATE_REPLYING, message=announcement)`
    - Call `ui.publish(EVENT_ASSISTANT_REPLY, text=announcement)`
    - If `speech_service is not None`: `speech_service.speak(announcement)` (catch `TTSError`, log error)
    - **Do NOT call `publish_idle_state()`** — cycle continues autonomously
    - `return` early
    - Else (no cycle or cycle inactive): fall through to existing behavior (announce completion + `publish_idle_state()`)

- [x] Update `src/runtime/tools/dispatch.py` to wire cycle on manual start/stop (AC: #4)
  - [x] Add import: `PomodoroCycleState` from `pomodoro`
  - [x] Add `pomodoro_cycle: PomodoroCycleState | None = None` to `RuntimeToolDispatcher.__init__()` and `self._pomodoro_cycle = pomodoro_cycle`
  - [x] In `_handle_pomodoro_tool_call()`, after `result = self._pomodoro_timer.apply(action, ...)` and when `result.accepted`, add cycle notifications:
    - `ACTION_START`: `if self._pomodoro_cycle is not None: self._pomodoro_cycle.begin_cycle(session_name=result.snapshot.session or DEFAULT_FOCUS_TOPIC_DE)`
    - `ACTION_ABORT`: `if self._pomodoro_cycle is not None: self._pomodoro_cycle.reset()`
    - `ACTION_RESET`: `if self._pomodoro_cycle is not None: self._pomodoro_cycle.begin_cycle(session_name=result.snapshot.session or DEFAULT_FOCUS_TOPIC_DE)`
  - [x] Add import: `DEFAULT_FOCUS_TOPIC_DE` from `shared.defaults`
  - [x] Do NOT add cycle notifications for `ACTION_PAUSE` or `ACTION_CONTINUE` — cycle pausing is not in scope for Story 3.2

- [x] Update `src/runtime/engine.py` to construct and wire `PomodoroCycleState` (AC: #1, #3)
  - [x] Add import: `PomodoroCycleState` from `pomodoro`
  - [x] Add `pomodoro_cycle: PomodoroCycleState | None = None` field to `RuntimeComponents` dataclass **with default `None`** to remain backward compatible with tests that construct `RuntimeComponents` without a cycle
  - [x] In `_build_runtime_components()`:
    - Create `pomodoro_cycle = PomodoroCycleState()` (uses default `work_seconds=DEFAULT_POMODORO_SECONDS`, `break_seconds=DEFAULT_SHORT_BREAK_SECONDS`)
    - Pass `pomodoro_cycle=pomodoro_cycle` to `RuntimeToolDispatcher(...)` constructor
    - Include `pomodoro_cycle=pomodoro_cycle` in the returned `RuntimeComponents(...)` instance
  - [x] In `RuntimeEngine.__init__()`:
    - Add `self._pomodoro_cycle = runtime_components.pomodoro_cycle`
  - [x] In `RuntimeEngine._emit_timer_ticks()`:
    - Pass `pomodoro_timer=self._pomodoro_timer, cycle=self._pomodoro_cycle` to `handle_pomodoro_tick(...)`

- [x] Write `tests/runtime/test_autonomous_transitions.py` — Story 3.2 AC coverage (AC: #5)
  - [x] Use same `_UIServerStub` + runtime package injection pattern from `test_ticks_state_flow.py`
  - [x] Import `PomodoroCycleState, PomodoroTimer` from `pomodoro`
  - [x] Import `handle_pomodoro_tick` from `runtime.ticks` (with TTS stub pattern)
  - [x] Test: **work→break transition fires on tick completion**
  - [x] Test: **break→work transition fires on break tick completion**
  - [x] Test: **session count increments only on work completion**
  - [x] Test: **cycle inactive → existing idle behavior preserved**
  - [x] Test: **cycle=None → existing idle behavior preserved (backward compat)**
  - [x] Test: **dispatcher begin_cycle called on start**
  - [x] Test: **dispatcher reset called on stop**

- [x] Run full test suite to verify no regressions (AC: #5)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — guard tests pass (13/13)
  - [x] `uv run pytest tests/` — all tests pass (185 total, 7 new)

## Dev Notes

### How Autonomous Transitions Work — Architecture Overview

The `PomodoroTimer.poll()` in `engine._emit_timer_ticks()` is called on every runtime loop iteration (~250ms cadence via `queue.get(timeout=0.25)`). When the timer completes:

1. `timer.poll()` returns `PomodoroTick(completed=True)` and internally sets `self._phase = PHASE_COMPLETED`
2. `engine._emit_timer_ticks()` passes the tick to `handle_pomodoro_tick()`
3. **NEW for Story 3.2**: `handle_pomodoro_tick()` detects `cycle.active` and calls `cycle.advance(timer)`
4. `cycle.advance()` calls `timer.apply(ACTION_RESET, session=..., duration_seconds=...)` which calls `_start_locked()`, transitioning timer back to `PHASE_RUNNING`
5. `handle_pomodoro_tick()` speaks the German announcement and publishes UI events — **does NOT call `publish_idle_state()`**
6. On the next engine loop, `timer.poll()` returns ticks for the new phase (short break countdown)

The key insight: `timer.apply(ACTION_RESET, ...)` works from `PHASE_COMPLETED` state (it calls `_start_locked()` unconditionally). After reset, `phase=PHASE_RUNNING` and `poll()` resumes firing ticks.

### What Already Exists — Do NOT Reinvent

**`PomodoroTimer` in `src/pomodoro/service.py`** — use as-is, no changes:
- `timer.apply(ACTION_RESET, session="Kurze Pause", duration_seconds=300)` → starts break timer from any phase
- `timer.apply(ACTION_RESET, session="Fokus", duration_seconds=1500)` → restarts work timer
- `timer.poll()` → fires ticks while `phase == PHASE_RUNNING`, returns `None` otherwise
- `PomodoroTick(snapshot, completed=True)` → emitted once when timer completes

**`handle_pomodoro_tick()` in `src/runtime/ticks.py`** — extend, do NOT replace:
- Currently: `tick.completed=True` → speak completion, publish replying state, call `publish_idle_state()`
- New behavior: when `cycle is not None and cycle.active` → autonomous transition instead of idle
- Old behavior (no cycle / cycle inactive) must remain untouched for tests and manual mode

**`RuntimeToolDispatcher._handle_pomodoro_tool_call()` in `src/runtime/tools/dispatch.py`** — add cycle hooks:
- Already handles `ACTION_START`, `ACTION_ABORT`, `ACTION_RESET` correctly
- Just need to call `cycle.begin_cycle()` or `cycle.reset()` after `result.accepted`
- No changes to the `match`/`case` dispatch structure

**`RuntimeComponents` in `src/runtime/engine.py`** — add optional field:
- Add `pomodoro_cycle: PomodoroCycleState | None = None` (default `None` preserves backward compat with tests)
- `_build_runtime_components()` always creates one in production

**`src/runtime/tools/messages.py`** — existing `default_pomodoro_text`, `pomodoro_status_message` etc. remain unchanged. Add new functions only.

### `PomodoroCycleState` Design Constraints

`PomodoroCycleState` is `@dataclass(slots=True)` (NOT frozen) because it holds mutable session state.

The `_active`, `_phase_type`, `_session_count`, `_work_session_name` fields have `default` + `init=False` in their `field()` definitions. In Python dataclasses with `slots=True`, private fields must use `field(default=..., init=False)`:
```python
from dataclasses import dataclass, field

@dataclass(slots=True)
class PomodoroCycleState:
    work_seconds: int = DEFAULT_POMODORO_SECONDS
    break_seconds: int = DEFAULT_SHORT_BREAK_SECONDS
    _active: bool = field(default=False, init=False)
    _phase_type: str = field(default=PHASE_TYPE_WORK, init=False)
    _session_count: int = field(default=0, init=False)
    _work_session_name: str = field(default="Fokus", init=False)
```

Do NOT add `frozen=True` — the state must be mutable across calls.

### `cycle.advance()` Implementation Details

```python
def advance(self, timer: PomodoroTimer) -> PhaseTransition:
    if self._phase_type == PHASE_TYPE_WORK:
        self._session_count += 1
        self._phase_type = PHASE_TYPE_SHORT_BREAK
        timer.apply(
            ACTION_RESET,
            session=DEFAULT_SHORT_BREAK_SESSION_NAME,
            duration_seconds=self.break_seconds,
        )
        return PhaseTransition(
            new_phase_type=PHASE_TYPE_SHORT_BREAK,
            session_count=self._session_count,
            duration_seconds=self.break_seconds,
        )
    else:  # PHASE_TYPE_SHORT_BREAK
        self._phase_type = PHASE_TYPE_WORK
        timer.apply(
            ACTION_RESET,
            session=self._work_session_name,
            duration_seconds=self.work_seconds,
        )
        return PhaseTransition(
            new_phase_type=PHASE_TYPE_WORK,
            session_count=self._session_count,
            duration_seconds=self.work_seconds,
        )
```

Note: `timer.apply()` uses `TYPE_CHECKING` guard for the import. In `cycle.py`, use:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .service import PomodoroTimer
```
This avoids any potential circular import at runtime while enabling type checking.

### `handle_pomodoro_tick()` New Branch — Exact Logic

```python
def handle_pomodoro_tick(
    tick: PomodoroTick,
    *,
    speech_service: TTSClient | None,
    logger: logging.Logger,
    ui: RuntimeUIPublisher,
    publish_idle_state: Callable[[], None],
    pomodoro_timer: PomodoroTimer | None = None,   # NEW
    cycle: PomodoroCycleState | None = None,        # NEW
) -> None:
    if tick.completed:
        if cycle is not None and cycle.active and pomodoro_timer is not None:
            # Autonomous transition: advance cycle and restart timer
            transition = cycle.advance(pomodoro_timer)
            if transition.new_phase_type == PHASE_TYPE_SHORT_BREAK:
                announcement = pomodoro_work_to_break_text(
                    transition.session_count, transition.duration_seconds
                )
            else:
                announcement = pomodoro_break_to_work_text()
            new_snapshot = pomodoro_timer.snapshot()
            ui.publish_pomodoro_update(
                new_snapshot,
                action=ACTION_COMPLETED,
                accepted=True,
                reason=REASON_COMPLETED,
                motivation=announcement,
            )
            ui.publish_state(STATE_REPLYING, message=announcement)
            ui.publish(EVENT_ASSISTANT_REPLY, text=announcement)
            if speech_service is not None:
                try:
                    speech_service.speak(announcement)
                except TTSError as error:
                    logger.error("TTS phase transition announcement failed: %s", error)
            # No publish_idle_state() — cycle continues
            return

        # Original completion behavior (manual mode or cycle inactive)
        completion_message = default_pomodoro_text(ACTION_COMPLETED, tick.snapshot)
        # ... existing code unchanged
```

### `dispatch.py` Cycle Hook — Exact Location

The cycle hooks go **after** `result.accepted` is established:
```python
result = self._pomodoro_timer.apply(action, session=focus_topic)
# ... response_text derivation unchanged ...

# NEW: notify cycle state
if self._pomodoro_cycle is not None and result.accepted:
    if action == ACTION_START:
        self._pomodoro_cycle.begin_cycle(
            session_name=result.snapshot.session or DEFAULT_FOCUS_TOPIC_DE
        )
    elif action == ACTION_ABORT:
        self._pomodoro_cycle.reset()
    elif action == ACTION_RESET:
        self._pomodoro_cycle.begin_cycle(
            session_name=result.snapshot.session or DEFAULT_FOCUS_TOPIC_DE
        )

self._ui.publish_pomodoro_update(...)  # unchanged
return response_text  # unchanged
```

Place this block between `response_text` derivation and `self._ui.publish_pomodoro_update(...)`.

### `RuntimeComponents` Field Order

New field must come LAST to preserve backward compat (existing code constructing `RuntimeComponents` positionally would break; keyword-only construction is fine). Since all existing tests use `components=RuntimeComponents(ui=..., ...)` with keyword arguments, adding with default at end is safe:

```python
@dataclass(slots=True)
class RuntimeComponents:
    ui: RuntimeUIPublisher
    pomodoro_timer: PomodoroTimer
    countdown_timer: PomodoroTimer
    dispatcher: RuntimeToolDispatcher
    event_queue: Queue[object]
    publisher: QueueEventPublisher
    utterance_executor: concurrent.futures.ThreadPoolExecutor
    pomodoro_cycle: PomodoroCycleState | None = None  # NEW — optional for test compat
```

### Test Pattern — Simulating Timer Completion Without Real Waits

Use `unittest.mock.patch("time.monotonic")` to make the timer think enough time has elapsed:

```python
from unittest.mock import patch
import time

timer = PomodoroTimer(duration_seconds=2)  # 2 second duration for speed
timer.apply("start", session="Fokus")

# Fast-forward time by patching monotonic
with patch("time.monotonic", return_value=time.monotonic() + 10.0):
    tick = timer.poll()  # should return PomodoroTick(completed=True)

self.assertIsNotNone(tick)
self.assertTrue(tick.completed)
```

Alternatively, use a very short `duration_seconds=1` and actually wait 1 second (acceptable for unit tests but slower). The `time.monotonic` patch is preferred for deterministic speed.

### Existing Test Compatibility

**`test_ticks_state_flow.py::test_pomodoro_completion_publishes_replying_then_idle`** — this test calls `handle_pomodoro_tick(tick, ..., publish_idle_state=...)` WITHOUT `cycle` parameter. Since `cycle=None` by default, the new branch is never entered. `publish_idle_state()` is still called. Test passes unchanged. ✓

**`test_pomodoro_session_control.py`** — constructs `RuntimeToolDispatcher(..., no pomodoro_cycle)`. With `pomodoro_cycle=None` default, cycle hooks are skipped. All 6 existing session control tests pass unchanged. ✓

**`test_contract_guards.py`** — scans source text for `dict[str, object]` in guarded files and `global _*`/`_*_INSTANCE` in worker files. New `cycle.py` is not a worker module. New signatures in `ticks.py` and `dispatch.py` must NOT use `dict[str, object]`. Use typed `PomodoroCycleState` and `PomodoroTimer` throughout. ✓

### `from __future__ import annotations` Compliance

Every new/modified `.py` file MUST have `from __future__ import annotations` as the first non-comment line. This includes `src/pomodoro/cycle.py` (new file).

### Import Order in New/Modified Files

```python
from __future__ import annotations
# 1. stdlib
# 2. third-party
# 3. local absolute (cross-package: from contracts..., from runtime..., from pomodoro...)
# 4. local relative (within-package: from .constants import ...)
# 5. TYPE_CHECKING guard
```

### Project Structure Notes

**Files to create:**
- `src/pomodoro/cycle.py` — `PomodoroCycleState` + `PhaseTransition`
- `tests/runtime/test_autonomous_transitions.py` — Story 3.2 AC coverage

**Files to modify:**
- `src/pomodoro/constants.py` — 4 new constants
- `src/pomodoro/__init__.py` — export `PomodoroCycleState`, `PhaseTransition`
- `src/runtime/ticks.py` — extended `handle_pomodoro_tick()` signature + autonomous branch
- `src/runtime/tools/dispatch.py` — `pomodoro_cycle` constructor param + cycle hooks
- `src/runtime/tools/messages.py` — 2 new German text functions
- `src/runtime/engine.py` — `RuntimeComponents.pomodoro_cycle` field + wiring in build/init/ticks

**No changes to:**
- `src/contracts/tool_contract.py` — no new tools
- `src/pomodoro/service.py` — `PomodoroTimer` is used as-is
- `src/llm/fast_path.py` — no new command routing
- `tests/runtime/test_ticks_state_flow.py` — passes unchanged (cycle=None default)
- `tests/runtime/test_pomodoro_session_control.py` — passes unchanged (no cycle arg)

**No new worker, protocol, or LLM grammar changes** — Story 3.2 touches only pomodoro cycle orchestration, tick handlers, and the dispatcher hook.

### Ordinal Session Numbering (Story 3.3 Note)

Story 3.3 handles the "after session 4 → long break" logic. For Story 3.2, the announcement text uses the plain integer session count (e.g. "Pomodoro-Einheit 2 abgeschlossen"). Do NOT implement ordinal German words ("Erste", "Zweite") now — that belongs in Story 3.3 which will refine cycle logic. Keep it simple here.

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 3.2 acceptance criteria (FR10, FR11, FR14)
- Previous story: `_bmad-output/implementation-artifacts/3-1-manual-pomodoro-session-control.md` — Dispatch architecture, test patterns, German message conventions
- Project context: `_bmad-output/project-context.md` — Tool system rules, testing patterns, `from __future__ import annotations` mandate
- `src/pomodoro/service.py` — `PomodoroTimer.poll()`, `PomodoroTimer.apply(ACTION_RESET, ...)` behaviour
- `src/pomodoro/constants.py` — `ACTION_RESET`, `DEFAULT_POMODORO_SECONDS`, `ACTIVE_PHASES`
- `src/runtime/ticks.py` — `handle_pomodoro_tick()` current implementation (base to extend)
- `src/runtime/engine.py` — `RuntimeComponents`, `_build_runtime_components()`, `_emit_timer_ticks()`
- `src/runtime/tools/dispatch.py` — `RuntimeToolDispatcher._handle_pomodoro_tool_call()` exact insertion point
- `src/runtime/tools/messages.py` — German message conventions, `format_duration()`, existing message functions
- `tests/runtime/test_ticks_state_flow.py` — `_UIServerStub` pattern + TTS stub + runtime package injection to reuse
- `tests/runtime/test_pomodoro_session_control.py` — `RuntimeToolDispatcher` test pattern to extend

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Implemented `PomodoroCycleState` + `PhaseTransition` in new `src/pomodoro/cycle.py` using `@dataclass(slots=True)` (mutable) and `@dataclass(frozen=True, slots=True)` patterns per project conventions.
- Extended `handle_pomodoro_tick()` with optional `pomodoro_timer` and `cycle` parameters; autonomous branch fires when `cycle.active` and suppresses `publish_idle_state()`.
- Wired `PomodoroCycleState` into `RuntimeToolDispatcher` (start/abort/reset hooks) and `RuntimeEngine` (`_build_runtime_components`, `__init__`, `_emit_timer_ticks`).
- Added two German text builders to `messages.py`: `pomodoro_work_to_break_text()` and `pomodoro_break_to_work_text()`.
- All 185 tests pass (178 existing + 7 new). All structural contract guards pass. No regressions.
- `time.monotonic` patching approach used in tests for deterministic timer completion without real waits.

### File List

**Created:**
- `src/pomodoro/cycle.py`
- `tests/runtime/test_autonomous_transitions.py`

**Modified:**
- `src/pomodoro/constants.py`
- `src/pomodoro/__init__.py`
- `src/runtime/ticks.py`
- `src/runtime/tools/dispatch.py`
- `src/runtime/tools/messages.py`
- `src/runtime/engine.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-03-02: Story 3.2 implemented — autonomous work-break phase transitions wired via PomodoroCycleState. New: src/pomodoro/cycle.py, tests/runtime/test_autonomous_transitions.py. Modified: constants.py, __init__.py, ticks.py, dispatch.py, messages.py, engine.py. 185 tests pass.
- 2026-03-02: Code review complete — 3 MEDIUM issues fixed: (1) added ACTION_RESET → begin_cycle() test; (2) publish_idle_state() now called after autonomous transition announcement so UI exits STATE_REPLYING; (3) cycle.py imports DEFAULT_FOCUS_TOPIC_DE instead of hardcoding "Fokus". 186 tests pass.

# Story 3.3: Long Break & Full Cycle Reset

Status: done

## Story

As a user,
I want the bot to automatically trigger a long break after my 4th work session and reset the cycle afterwards,
so that the full Pomodoro method runs without me tracking session count or initiating any action after the first start command.

## Acceptance Criteria

1. **Given** three work sessions and three short breaks have completed autonomously
   **When** the 4th work session duration expires
   **Then** the bot speaks a German long break announcement (e.g. "Pomodoro-Einheit 4 abgeschlossen. Lange Pause — 15 Minuten. Gut gemacht.")
   **And** the `PomodoroCycleState` transitions to `PHASE_TYPE_LONG_BREAK` state with a 15-minute timer (`DEFAULT_LONG_BREAK_SECONDS = 15 * 60`)
   **And** no short break is triggered after session 4 — the long break fires instead

2. **Given** a long break phase is active (15 minutes by default)
   **When** the long break duration expires
   **Then** the bot speaks a German cycle reset announcement (e.g. "Lange Pause vorbei. Neuer Zyklus beginnt.")
   **And** `PomodoroCycleState._session_count` is reset to `0` and `_phase_type` returns to `PHASE_TYPE_WORK`
   **And** the `PomodoroTimer` resets to `_work_session_name` and `work_seconds` duration — the full 4-session cycle repeats from the beginning without any user command

3. **Given** the full cycle (4 × work + 3 × short break + 1 × long break + reset) runs end-to-end
   **When** each transition fires
   **Then** a spoken German announcement accompanies every boundary — no silent transitions
   **And** the system state is consistent at every boundary: session count, phase type, and timer values are correct

4. **Given** long break and cycle reset logic is implemented
   **When** `uv run pytest tests/pomodoro/` is executed
   **Then** the full 4-session cycle is exercisable with a time-stubbed `PomodoroTimer` — session count, phase sequence, and announcement triggers are all verified without real elapsed time
   **And** all existing 186 tests continue to pass without regressions

## Tasks / Subtasks

- [x] Add new constants to `src/pomodoro/constants.py` (AC: #1, #2)
  - [x] Add `DEFAULT_LONG_BREAK_SECONDS = 15 * 60`
  - [x] Add `DEFAULT_LONG_BREAK_SESSION_NAME = "Lange Pause"` (timer session name during long break)
  - [x] Add `PHASE_TYPE_LONG_BREAK = "long_break"` (cycle tracker state string — NOT a PomodoroPhase)
  - [x] Add `SESSIONS_PER_CYCLE = 4` (number of completed work sessions before long break triggers)

- [x] Update `PhaseTransition` in `src/pomodoro/cycle.py` — add `previous_phase_type` field (AC: #3)
  - [x] Add `previous_phase_type: str` as a required field in `PhaseTransition` dataclass (field order: `new_phase_type`, `previous_phase_type`, `session_count`, `duration_seconds`)
  - [x] Update all `PhaseTransition(...)` constructor calls in `advance()` to include `previous_phase_type`
  - [x] **Note:** No tests construct `PhaseTransition` directly — only `PomodoroCycleState.advance()` does

- [x] Add `long_break_seconds` field to `PomodoroCycleState` (AC: #1, #2)
  - [x] Add `long_break_seconds: int = DEFAULT_LONG_BREAK_SECONDS` as a new init field (place after `break_seconds`)
  - [x] Import `DEFAULT_LONG_BREAK_SECONDS` at the top of `cycle.py`
  - [x] Existing `PomodoroCycleState()` and `PomodoroCycleState(work_seconds=..., break_seconds=...)` calls remain valid — the default handles them

- [x] Extend `PomodoroCycleState.advance()` for long break and cycle reset (AC: #1, #2, #3)
  - [x] Import `DEFAULT_LONG_BREAK_SESSION_NAME`, `PHASE_TYPE_LONG_BREAK`, `SESSIONS_PER_CYCLE` from `.constants`
  - [x] Restructure the `PHASE_TYPE_WORK` branch to check session count after incrementing:
    - `self._session_count += 1`
    - `if self._session_count >= SESSIONS_PER_CYCLE` → transition to `PHASE_TYPE_LONG_BREAK`
    - `else` → transition to `PHASE_TYPE_SHORT_BREAK` (existing logic, add `previous_phase_type=PHASE_TYPE_WORK`)
  - [x] Add a new `elif self._phase_type == PHASE_TYPE_LONG_BREAK` branch (before the `else` / short_break branch):
    - `self._session_count = 0` (cycle resets for fresh start)
    - `self._phase_type = PHASE_TYPE_WORK`
    - `timer.apply(ACTION_RESET, session=self._work_session_name, duration_seconds=self.work_seconds)`
    - Return `PhaseTransition(new_phase_type=PHASE_TYPE_WORK, previous_phase_type=PHASE_TYPE_LONG_BREAK, session_count=self._session_count, duration_seconds=self.work_seconds)`
  - [x] Update existing `PHASE_TYPE_SHORT_BREAK` branch to include `previous_phase_type=PHASE_TYPE_SHORT_BREAK` in the returned `PhaseTransition`

- [x] Add German long break announcement functions to `src/runtime/tools/messages.py` (AC: #1, #2, #3)
  - [x] Add `pomodoro_work_to_long_break_text(session_count: int, break_seconds: int) -> str`
    - Returns e.g. `f"Pomodoro-Einheit {session_count} abgeschlossen. Lange Pause — {break_seconds // 60} Minuten. Gut gemacht."`
    - Signature mirrors `pomodoro_work_to_break_text(session_count, break_seconds)` for consistency
  - [x] Add `pomodoro_long_break_to_work_text() -> str`
    - Returns `"Lange Pause vorbei. Neuer Zyklus beginnt."`
    - Signature mirrors `pomodoro_break_to_work_text()` (no arguments)

- [x] Update `src/runtime/ticks.py` to handle long break transitions (AC: #1, #2, #3)
  - [x] Add import `PHASE_TYPE_LONG_BREAK` from `pomodoro.constants`
  - [x] Add imports `pomodoro_work_to_long_break_text, pomodoro_long_break_to_work_text` from `.tools.messages`
  - [x] Replace the two-branch `if/else` announcement block with a four-branch `if/elif/elif/else`:
    - `if transition.new_phase_type == PHASE_TYPE_SHORT_BREAK:` → `pomodoro_work_to_break_text(...)`
    - `elif transition.new_phase_type == PHASE_TYPE_LONG_BREAK:` → `pomodoro_work_to_long_break_text(...)`
    - `elif transition.previous_phase_type == PHASE_TYPE_SHORT_BREAK:` → `pomodoro_break_to_work_text()`
    - `else:` (long break → work) → `pomodoro_long_break_to_work_text()`

- [x] Write `tests/pomodoro/test_full_cycle.py` — Story 3.3 AC coverage (AC: #4)
  - [x] Import `PomodoroCycleState, PomodoroTimer` from `pomodoro`
  - [x] Import `PHASE_TYPE_LONG_BREAK, PHASE_TYPE_SHORT_BREAK, PHASE_TYPE_WORK, SESSIONS_PER_CYCLE` from `pomodoro.constants`
  - [x] Use `_make_completed_tick(timer)` helper with `patch("time.monotonic", return_value=time.monotonic() + 100_000.0)` (same pattern as `test_autonomous_transitions.py`)
  - [x] For tests that exercise `handle_pomodoro_tick`: use the runtime package injection + TTS stub pattern from `test_autonomous_transitions.py`
  - [x] Test: **session 4 work completion → long break (not short break)**
    - Advance 4 work completions, each preceded by its short break; confirm 4th work → `PHASE_TYPE_LONG_BREAK`
    - Timer session becomes `"Lange Pause"`, duration becomes `DEFAULT_LONG_BREAK_SECONDS`
  - [x] Test: **sessions 1–3 trigger short break, not long break**
    - After sessions 1, 2, 3 completions → `cycle.phase_type == PHASE_TYPE_SHORT_BREAK`
    - Only after session 4 → `cycle.phase_type == PHASE_TYPE_LONG_BREAK`
  - [x] Test: **long break completion → work with full cycle reset**
    - After long break tick: `cycle.phase_type == PHASE_TYPE_WORK`
    - `cycle.session_count == 0` (reset for new cycle)
    - Timer session name matches original `_work_session_name`, duration matches `work_seconds`
  - [x] Test: **full 8-transition sequence** (W→SB, SB→W, W→SB, SB→W, W→SB, SB→W, W→LB, LB→W)
    - All 8 transitions produce the correct `phase_type` in the correct order
    - `session_count == 0` at end of full cycle
  - [x] Test: **cycle repeats after reset** — after LB→W, session 4 again triggers long break
  - [x] Test: **announcement text is non-empty at every transition** (via `handle_pomodoro_tick` + `EVENT_ASSISTANT_REPLY` payload check)

- [x] Run full test suite to verify no regressions (AC: #4)
  - [x] `uv run pytest tests/pomodoro/` — all pomodoro tests pass
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — guard tests pass
  - [x] `uv run pytest tests/runtime/test_autonomous_transitions.py` — all 7 existing Story 3.2 tests pass unchanged
  - [x] `uv run pytest tests/` — all tests pass (186 existing + 7 new = 193 total)

## Dev Notes

### Complete Phase Transition Graph After This Story

```
PHASE_TYPE_WORK (session_count < SESSIONS_PER_CYCLE)  →  PHASE_TYPE_SHORT_BREAK
PHASE_TYPE_WORK (session_count == SESSIONS_PER_CYCLE) →  PHASE_TYPE_LONG_BREAK   ← NEW
PHASE_TYPE_SHORT_BREAK                                →  PHASE_TYPE_WORK
PHASE_TYPE_LONG_BREAK                                 →  PHASE_TYPE_WORK + reset  ← NEW
```

The `PomodoroTimer` layer is unaware of "short" vs "long" break — it only sees session names and durations. `PHASE_TYPE_LONG_BREAK` is purely an internal cycle tracker state that controls which German announcement and timer duration are used.

### `PhaseTransition` — Adding `previous_phase_type` (Required Field)

```python
@dataclass(frozen=True, slots=True)
class PhaseTransition:
    new_phase_type: str
    previous_phase_type: str  # NEW — always set by advance(); needed by ticks.py announcements
    session_count: int
    duration_seconds: int
```

`previous_phase_type` is needed in `ticks.py` to differentiate "work resumes after short break" from "work resumes after long break" — both produce `new_phase_type=PHASE_TYPE_WORK` but require different German announcement text.

**Backward compat:** `PhaseTransition` is only ever constructed inside `PomodoroCycleState.advance()`. No tests construct it directly (verified in `test_autonomous_transitions.py`). The existing 7 Story 3.2 tests pass unchanged because they check `cycle.phase_type` and `cycle.session_count`, not `PhaseTransition` fields.

### `PomodoroCycleState` — Adding `long_break_seconds` (Default Field)

```python
@dataclass(slots=True)
class PomodoroCycleState:
    work_seconds: int = DEFAULT_POMODORO_SECONDS
    break_seconds: int = DEFAULT_SHORT_BREAK_SECONDS
    long_break_seconds: int = DEFAULT_LONG_BREAK_SECONDS   # NEW — has default, backward compatible
    _active: bool = field(default=False, init=False)
    _phase_type: str = field(default=PHASE_TYPE_WORK, init=False)
    _session_count: int = field(default=0, init=False)
    _work_session_name: str = field(default=DEFAULT_FOCUS_TOPIC_DE, init=False)
```

`engine.py`'s `_build_runtime_components()` creates `PomodoroCycleState()` with no arguments — still valid. Tests in `test_autonomous_transitions.py` use `PomodoroCycleState()` and `PomodoroCycleState(work_seconds=2, break_seconds=2)` — both still valid.

### `advance()` — Complete Extended Implementation

```python
def advance(self, timer: PomodoroTimer) -> PhaseTransition:
    """Advance to the next phase, reset the timer, and return the transition."""
    if self._phase_type == PHASE_TYPE_WORK:
        self._session_count += 1
        if self._session_count >= SESSIONS_PER_CYCLE:
            # Long break after completing the Nth work session
            self._phase_type = PHASE_TYPE_LONG_BREAK
            timer.apply(
                ACTION_RESET,
                session=DEFAULT_LONG_BREAK_SESSION_NAME,
                duration_seconds=self.long_break_seconds,
            )
            return PhaseTransition(
                new_phase_type=PHASE_TYPE_LONG_BREAK,
                previous_phase_type=PHASE_TYPE_WORK,
                session_count=self._session_count,
                duration_seconds=self.long_break_seconds,
            )
        else:
            # Short break between work sessions
            self._phase_type = PHASE_TYPE_SHORT_BREAK
            timer.apply(
                ACTION_RESET,
                session=DEFAULT_SHORT_BREAK_SESSION_NAME,
                duration_seconds=self.break_seconds,
            )
            return PhaseTransition(
                new_phase_type=PHASE_TYPE_SHORT_BREAK,
                previous_phase_type=PHASE_TYPE_WORK,
                session_count=self._session_count,
                duration_seconds=self.break_seconds,
            )
    elif self._phase_type == PHASE_TYPE_LONG_BREAK:
        # Cycle reset: session count back to 0, start fresh work phase
        self._session_count = 0
        self._phase_type = PHASE_TYPE_WORK
        timer.apply(
            ACTION_RESET,
            session=self._work_session_name,
            duration_seconds=self.work_seconds,
        )
        return PhaseTransition(
            new_phase_type=PHASE_TYPE_WORK,
            previous_phase_type=PHASE_TYPE_LONG_BREAK,
            session_count=self._session_count,  # 0 after reset
            duration_seconds=self.work_seconds,
        )
    else:  # PHASE_TYPE_SHORT_BREAK → back to work
        self._phase_type = PHASE_TYPE_WORK
        timer.apply(
            ACTION_RESET,
            session=self._work_session_name,
            duration_seconds=self.work_seconds,
        )
        return PhaseTransition(
            new_phase_type=PHASE_TYPE_WORK,
            previous_phase_type=PHASE_TYPE_SHORT_BREAK,
            session_count=self._session_count,
            duration_seconds=self.work_seconds,
        )
```

**Why `PHASE_TYPE_LONG_BREAK` branch comes BEFORE the `else` (short_break) branch:** The `else` clause is a fallback for `PHASE_TYPE_SHORT_BREAK`. If long break is added as an `else`, it would accidentally catch short_break phase too. Use explicit `elif` for each phase type.

### `ticks.py` — Announcement Selection Block (Complete Replacement)

Replace the current two-branch block:
```python
# OLD (Story 3.2)
if transition.new_phase_type == PHASE_TYPE_SHORT_BREAK:
    announcement = pomodoro_work_to_break_text(
        transition.session_count, transition.duration_seconds
    )
else:
    announcement = pomodoro_break_to_work_text()
```

With the four-branch block:
```python
# NEW (Story 3.3)
if transition.new_phase_type == PHASE_TYPE_SHORT_BREAK:
    announcement = pomodoro_work_to_break_text(
        transition.session_count, transition.duration_seconds
    )
elif transition.new_phase_type == PHASE_TYPE_LONG_BREAK:
    announcement = pomodoro_work_to_long_break_text(
        transition.session_count, transition.duration_seconds
    )
elif transition.previous_phase_type == PHASE_TYPE_SHORT_BREAK:
    announcement = pomodoro_break_to_work_text()
else:  # PHASE_TYPE_LONG_BREAK → PHASE_TYPE_WORK
    announcement = pomodoro_long_break_to_work_text()
```

The `else` branch is reached only when `new_phase_type == PHASE_TYPE_WORK` AND `previous_phase_type == PHASE_TYPE_LONG_BREAK` (cycle reset case).

### German Announcement Text Conventions

Following the naming and tone pattern in `messages.py`:

```python
def pomodoro_work_to_long_break_text(session_count: int, break_seconds: int) -> str:
    """Return German announcement for work→long_break phase transition."""
    return (
        f"Pomodoro-Einheit {session_count} abgeschlossen. "
        f"Lange Pause — {break_seconds // 60} Minuten. Gut gemacht."
    )

def pomodoro_long_break_to_work_text() -> str:
    """Return German announcement for long_break→work cycle reset."""
    return "Lange Pause vorbei. Neuer Zyklus beginnt."
```

`session_count` is always `SESSIONS_PER_CYCLE = 4` when `pomodoro_work_to_long_break_text` is called, but the function accepts it as a parameter (consistent with `pomodoro_work_to_break_text` which also receives `session_count`).

### Test File Structure for `tests/pomodoro/test_full_cycle.py`

`tests/pomodoro/__init__.py` already exists. The new file follows the same import conventions as `test_timer_characterization.py` (direct pomodoro imports, no sys.modules injection needed for pure cycle tests).

For tests that need `handle_pomodoro_tick`, use the same runtime package injection + TTS stub pattern from `test_autonomous_transitions.py`:

```python
# Copied verbatim from test_autonomous_transitions.py — do not simplify
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg

def _build_tts_stub_modules():
    ...  # same stub as in test_autonomous_transitions.py

with patch.dict(sys.modules, _build_tts_stub_modules()):
    from runtime.ticks import handle_pomodoro_tick
```

The `_make_completed_tick(timer)` helper:
```python
def _make_completed_tick(timer: PomodoroTimer):
    future_time = time.monotonic() + 100_000.0
    with patch("time.monotonic", return_value=future_time):
        tick = timer.poll()
    return tick
```

To drive the full 4-session cycle in a test without real timers:
```python
def _drive_full_cycle(cycle, timer):
    """Drive 4 work + 3 short_break + 1 long_break transitions."""
    transitions = []
    # Simulate 4 work sessions and 3 short breaks + long break
    for _ in range(4):
        # Work session completes
        tick = _make_completed_tick(timer)
        transitions.append(cycle.advance(timer))  # may be short_break or long_break
        if cycle.phase_type != PHASE_TYPE_LONG_BREAK:
            # Short break completes
            tick = _make_completed_tick(timer)
            transitions.append(cycle.advance(timer))  # back to work
    return transitions
```

Alternatively, call `cycle.advance(timer)` directly in tests without needing real ticks — `advance()` works on the cycle state independently of `handle_pomodoro_tick`.

### Structural Contract Guard Compliance

New code must NOT contain:
- `dict[str, object]` in any function signature in `ticks.py`, `dispatch.py`, `calendar.py`, or `ui.py`
- `global _variable_name` patterns or `_SOMETHING_INSTANCE` names in worker modules

`PHASE_TYPE_LONG_BREAK` is a string constant imported from `pomodoro.constants` — never hardcoded inline.

`from __future__ import annotations` must be the first non-comment line in every modified file.

### Existing Tests — Zero Changes Required

| Test file | Status | Reason |
|---|---|---|
| `test_autonomous_transitions.py` | ✓ Pass unchanged | Tests check `cycle.phase_type`/`session_count`, not `PhaseTransition` fields; 2-session runs stay below `SESSIONS_PER_CYCLE=4` |
| `test_pomodoro_session_control.py` | ✓ Pass unchanged | No `PhaseTransition` usage |
| `test_ticks_state_flow.py` | ✓ Pass unchanged | `cycle=None` default path untouched |
| `test_timer_characterization.py` | ✓ Pass unchanged | `PomodoroTimer` has no changes |
| `test_contract_guards.py` | ✓ Pass if rules followed | Run explicitly before marking complete |

### `src/runtime/engine.py` — No Changes Required

`_build_runtime_components()` creates `PomodoroCycleState()` with no args. Since `long_break_seconds` has a default, this continues to work. No other engine changes are needed for Story 3.3.

### `src/pomodoro/__init__.py` — No Changes Required

`PhaseTransition` and `PomodoroCycleState` are already exported. The new `PHASE_TYPE_LONG_BREAK` constant lives in `pomodoro.constants` — callers import it from there directly (as `ticks.py` already does for `PHASE_TYPE_SHORT_BREAK`).

### Story 3.4 Context (Do Not Implement)

Story 3.4 (Web UI Pomodoro State Synchronisation) will need to broadcast a `STATE_POMODORO_LONG_BREAK` constant via `contracts/ui_protocol.py`. The `publish_pomodoro_update()` calls in `ticks.py` already propagate the new `PhaseTransition` data — Story 3.4 will handle the UI constant naming. Do NOT define UI state constants here.

### Project Structure Notes

**Files to create:**
- `tests/pomodoro/test_full_cycle.py` — Story 3.3 AC coverage

**Files to modify:**
- `src/pomodoro/constants.py` — 4 new constants
- `src/pomodoro/cycle.py` — `PhaseTransition.previous_phase_type` field + `PomodoroCycleState.long_break_seconds` field + `advance()` extension
- `src/runtime/tools/messages.py` — 2 new German text functions
- `src/runtime/ticks.py` — 2 new imports + 4-branch announcement block

**No changes to:**
- `src/pomodoro/__init__.py` — already exports `PhaseTransition`, `PomodoroCycleState`
- `src/pomodoro/service.py` — `PomodoroTimer.apply(ACTION_RESET, ...)` used as-is
- `src/runtime/tools/dispatch.py` — cycle hooks for start/stop/reset unchanged
- `src/runtime/engine.py` — `PomodoroCycleState()` with no args still valid
- `src/contracts/tool_contract.py` — no new tools
- `src/llm/fast_path.py` — no new command routing
- `tests/runtime/test_autonomous_transitions.py` — passes unchanged

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 3.3 acceptance criteria (FR12, FR13, FR14)
- Previous story: `_bmad-output/implementation-artifacts/3-2-autonomous-work-break-phase-transitions.md` — `PomodoroCycleState` design constraints, `PhaseTransition` definition, `advance()` exact implementation, test patterns
- Project context: `_bmad-output/project-context.md` — `from __future__ import annotations` mandate, `@dataclass(frozen=True, slots=True)` rules, German/English language rules, testing patterns
- `src/pomodoro/cycle.py` — `PomodoroCycleState.advance()` base to extend (Story 3.2 implementation)
- `src/pomodoro/constants.py` — Existing constants (add 4 new ones)
- `src/runtime/ticks.py` — `handle_pomodoro_tick()` announcement block to replace
- `src/runtime/tools/messages.py` — German message conventions, `pomodoro_work_to_break_text` / `pomodoro_break_to_work_text` as models
- `tests/runtime/test_autonomous_transitions.py` — `_make_completed_tick`, `_UIServerStub`, runtime injection pattern to reuse
- `tests/pomodoro/test_timer_characterization.py` — Existing test in target directory for structural reference

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation proceeded cleanly with no debugging required.

### Completion Notes List

- Added 4 new constants to `src/pomodoro/constants.py`: `PHASE_TYPE_LONG_BREAK`, `DEFAULT_LONG_BREAK_SECONDS`, `DEFAULT_LONG_BREAK_SESSION_NAME`, `SESSIONS_PER_CYCLE`
- Added `previous_phase_type: str` required field to `PhaseTransition` dataclass; all 3 constructor call sites in `advance()` updated
- Added `long_break_seconds: int = DEFAULT_LONG_BREAK_SECONDS` to `PomodoroCycleState` with default — backward compatible with all existing callers
- Extended `PomodoroCycleState.advance()` from 2-branch to 3-branch: WORK→short_break, WORK→long_break (after 4th session), LONG_BREAK→work+reset, SHORT_BREAK→work
- Added `pomodoro_work_to_long_break_text()` and `pomodoro_long_break_to_work_text()` to `messages.py`
- Extended `handle_pomodoro_tick()` announcement block from 2-branch to 4-branch using `transition.new_phase_type` and `transition.previous_phase_type`
- All 193 tests pass (186 existing + 7 new); zero regressions; contract guards clean

### File List

**Created:**
- `tests/pomodoro/test_full_cycle.py`

**Modified:**
- `src/pomodoro/constants.py`
- `src/pomodoro/cycle.py`
- `src/runtime/tools/messages.py`
- `src/runtime/ticks.py`

### Senior Developer Review (AI)

Reviewed by: Shrink0r on 2026-03-02

**Outcome: Approved** — all 4 ACs implemented, 193 tests passing, 0 regressions.

**Issues found and fixed (4 total):**
- [MEDIUM] Removed unused import `DEFAULT_SHORT_BREAK_SECONDS` from `tests/pomodoro/test_full_cycle.py`
- [LOW] Updated stale `phase_type` property docstring in `cycle.py` to include `PHASE_TYPE_LONG_BREAK`
- [LOW] Removed assigned-but-unused `tick` variable captures in `test_sessions_1_to_3_trigger_short_break_not_long_break`
- [LOW] Strengthened `assertIn("15", text)` → `assertIn("15 Minuten", text)` in announcement test

### Change Log

- 2026-03-02: Implemented Story 3.3 — long break after 4th work session + full cycle reset. Added `PHASE_TYPE_LONG_BREAK` state, `SESSIONS_PER_CYCLE=4` constant, `previous_phase_type` field to `PhaseTransition`, `long_break_seconds` field to `PomodoroCycleState`, extended `advance()` with long break branch, added 2 German announcement functions, extended ticks.py announcement block from 2 to 4 branches. 7 new tests covering full 8-transition cycle sequence.
- 2026-03-02: Code review — removed unused import, fixed stale docstring, cleaned up unused tick variables, strengthened text assertion. Status set to done.

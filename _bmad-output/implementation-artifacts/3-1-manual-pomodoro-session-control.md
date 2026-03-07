# Story 3.1: Manual Pomodoro Session Control

Status: done

## Story

As a user,
I want to start, stop, and query a Pomodoro session via voice command,
so that I can initiate and control focus sessions hands-free with spoken German confirmations.

## Acceptance Criteria

1. **Given** the assistant is idle and no Pomodoro session is active
   **When** the user says a start command (e.g. "Starte eine Pomodoro-Session")
   **Then** the `PomodoroTimer` transitions to the `running` state with the work phase active
   **And** the TTS speaks a German confirmation (e.g. "Ich starte jetzt deine Pomodoro Sitzung fuer Fokus.")
   **And** the session start time is recorded for accurate phase timing

2. **Given** a Pomodoro session is active
   **When** the user says a stop command (e.g. "Stoppe die Pomodoro-Session")
   **Then** the `PomodoroTimer` transitions to `aborted` state and all timers are cancelled
   **And** the TTS speaks a German confirmation (e.g. "Ich stoppe die Pomodoro Sitzung fuer Fokus.")
   **And** session state is fully reset — a subsequent start command begins a fresh cycle

3. **Given** a Pomodoro session is active
   **When** the user says a status query (e.g. "Wie lange läuft die Session schon?")
   **Then** the TTS speaks the current phase and remaining time in German (e.g. "Pomodoro 'Fokus' laeuft (18:30 verbleibend)")
   **And** the response is generated without disrupting the running phase timer

4. **Given** no Pomodoro session is active
   **When** the user says a stop or status command
   **Then** the TTS speaks an appropriate German response indicating no active session
   **And** the system remains in idle state — no error or crash

5. **Given** Pomodoro voice commands are implemented
   **When** `uv run pytest tests/` is executed
   **Then** all `PomodoroTimer` state transitions for start/stop/status are covered by unit tests using stubs — no hardware or real timers required
   **And** guard tests in `tests/runtime/test_contract_guards.py` pass

## Tasks / Subtasks

- [x] Add `TOOL_STATUS_POMODORO` constant to `src/contracts/tool_contract.py` (AC: #3, #4)
  - [x] Define `TOOL_STATUS_POMODORO = "status_pomodoro_session"`
  - [x] Append to `TOOL_NAME_ORDER` tuple (after `TOOL_RESET_POMODORO`)
  - [x] Add to `POMODORO_TOOL_NAMES` frozenset
  - [x] Add to `TOOLS_WITHOUT_ARGUMENTS` frozenset (no arguments needed for status query)
  - [x] Do NOT add to `POMODORO_TOOL_TO_RUNTIME_ACTION` — status is a read-only query, not a state mutation

- [x] Add status query detection to `src/llm/parser_rules.py` (AC: #3)
  - [x] Add `looks_like_pomodoro_status(lowered_prompt: str) -> bool` function
  - [x] Pattern should match: "wie lange", "wie viel", "status", "wie viel zeit", "wie steht", "noch.*zeit", "verbleibend", "wie laeuft"
  - [x] Only fires when `has_pomodoro_context()` is also true (avoid false positives)

- [x] Update `src/llm/fast_path.py` to route status queries (AC: #3)
  - [x] Import `looks_like_pomodoro_status` from `parser_rules`
  - [x] Import `TOOL_STATUS_POMODORO` from `contracts.tool_contract`
  - [x] In `_infer_tool_call()`: add check for `looks_like_pomodoro_status(lowered)` + `has_pomodoro(lowered)` → return `_tool_call(TOOL_STATUS_POMODORO, {})`
  - [x] Place this check BEFORE the generic `detect_action()` path so status intent is not swallowed by action detection

- [x] Add status query dispatch arm in `src/runtime/tools/dispatch.py` (AC: #3, #4)
  - [x] Add `_tc.TOOL_STATUS_POMODORO` to the existing pomodoro `case` group in `handle_tool_call()`
  - [x] Add `_handle_pomodoro_status_query()` private method to `RuntimeToolDispatcher`
  - [x] `_handle_pomodoro_status_query()` returns `pomodoro_status_message(self._pomodoro_timer.snapshot())`
  - [x] For idle phase: `pomodoro_status_message` already returns "Bereit" — enhance with "Keine aktive Pomodoro-Sitzung." for clarity (update `messages.py`)
  - [x] No UI event published for status query (read-only, no state change)

- [x] Update German status message for idle in `src/runtime/tools/messages.py` (AC: #4)
  - [x] In `pomodoro_status_message()`: change idle fallback from "Bereit" to "Keine aktive Pomodoro-Sitzung."

- [x] Write new test file `tests/runtime/test_pomodoro_session_control.py` (AC: #5)
  - [x] Test: start when idle → `running`, German confirmation text
  - [x] Test: stop when running → `aborted`, German confirmation text
  - [x] Test: status when running → German remaining time text
  - [x] Test: stop when idle → rejection text "Es gibt keine aktive Pomodoro Sitzung."
  - [x] Test: status when idle → "Keine aktive Pomodoro-Sitzung." text
  - [x] Test: abort then start again → fresh `running` state (session reset)
  - [x] Use same `RuntimeToolDispatcher` + `_UIServerStub` pattern from `test_tool_dispatch.py`

- [x] Run full test suite to verify no regressions (AC: #5)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — guard tests pass
  - [x] `uv run pytest tests/` — all tests pass, zero regressions

## Dev Notes

### What Already Exists — Do NOT Reinvent

**`src/pomodoro/service.py` — `PomodoroTimer`** — fully implemented; use as-is:
- `timer.apply("start", session="Fokus")` → `PomodoroActionResult(accepted=True, reason="started", snapshot=...)`
- `timer.apply("abort")` → accepted if phase in `ACTIVE_PHASES` (running or paused); reason="aborted"
- `timer.apply("abort")` when idle → `accepted=False, reason="not_active"`
- `timer.snapshot()` → `PomodoroSnapshot(phase, session, duration_seconds, remaining_seconds)`
- `timer.poll()` → tick-based polling for autonomous transitions (not needed for this story — Story 3.2)

**`src/contracts/tool_contract.py`** — tools `TOOL_START_POMODORO` → `TOOL_RESET_POMODORO` already defined.
All map to `POMODORO_TOOL_TO_RUNTIME_ACTION` and are already dispatched by `dispatch.py`.
Only NEW addition for this story: `TOOL_STATUS_POMODORO`.

**`src/runtime/tools/dispatch.py` — `RuntimeToolDispatcher`**:
- `handle_tool_call()` already uses structural pattern matching (`match raw_name: case ...`)
- Pomodoro tools already go to `_handle_pomodoro_tool_call()` which calls `PomodoroTimer.apply(action)`
- The `TOOL_STATUS_POMODORO` case must be routed SEPARATELY (it's read-only, not in `POMODORO_TOOL_TO_RUNTIME_ACTION`)
- Add `TOOL_STATUS_POMODORO` to the pomodoro `case` group OR as its own arm — separate method required

**`src/runtime/tools/messages.py`** — German messages already built:
- `default_pomodoro_text(action, snapshot)` → covers start, pause, continue, abort, completed
- `pomodoro_rejection_text(action, reason)` → covers not_running, not_paused, not_active, timer_active
- `pomodoro_status_message(snapshot)` → already formats running/paused/idle state in German
- `format_duration(seconds)` → already formats `MM:SS`

**`src/llm/fast_path.py`** — already routes:
- `has_pomodoro_context() + detect_action("start")` → `TOOL_START_POMODORO`
- `has_pomodoro_context() + detect_action("stop")` → `TOOL_STOP_POMODORO`
- Status queries do NOT match `detect_action()` (no action keyword) — need new function

**`src/llm/parser_rules.py`** — `has_pomodoro_context()` uses: `r"\b(pomodoro|fokus|fokussitzung|sitzung)\b"`

**`tests/runtime/test_tool_dispatch.py`** — existing pattern for `RuntimeToolDispatcher` tests with `_UIServerStub`.
Extend this or add a new file. Prefer NEW file `test_pomodoro_session_control.py` to isolate Story 3.1 ACs.

### Dispatch Architecture for `TOOL_STATUS_POMODORO`

The existing `_handle_pomodoro_tool_call()` starts with:
```python
action = POMODORO_TOOL_TO_RUNTIME_ACTION[tool_name]
```
This would raise `KeyError` for `TOOL_STATUS_POMODORO`. Therefore:
- Route `TOOL_STATUS_POMODORO` to a SEPARATE `_handle_pomodoro_status_query()` method
- In `handle_tool_call()` match statement, either add it as its own `case` arm, OR add it to the grouped pomodoro case with a pre-dispatch branch

Cleanest approach:
```python
case _tc.TOOL_STATUS_POMODORO:
    return self._handle_pomodoro_status_query(assistant_text)
```
This is the minimal diff and least-risk change to the dispatch.

### Status Query Response Text

`pomodoro_status_message(snapshot)` already returns:
- Running: `"Pomodoro 'Fokus' laeuft (18:30 verbleibend)"`
- Paused: `"Pomodoro 'Fokus' pausiert (18:30 verbleibend)"`
- Completed: `"Pomodoro 'Fokus' abgeschlossen"`
- Aborted: `"Pomodoro 'Fokus' gestoppt"`
- Idle fallback: `"Bereit"` ← Change to `"Keine aktive Pomodoro-Sitzung."` for clarity

The `_handle_pomodoro_status_query()` method returns this directly as the TTS text.
It does NOT call `PomodoroTimer.apply()` and does NOT publish a UI event.

### fast_path Status Detection

New function in `src/llm/parser_rules.py`:
```python
def looks_like_pomodoro_status(lowered_prompt: str) -> bool:
    """Return whether text looks like a pomodoro status/remaining-time query."""
    has_status_intent = bool(re.search(
        r"\b(wie lange|wie viel|status|wie steht|wie laeuft|noch|verbleibend|restzeit|wie weit)\b",
        lowered_prompt,
    ))
    return has_status_intent
```
Used in `fast_path._infer_tool_call()`:
```python
if looks_like_pomodoro_status(lowered) and has_pomodoro_context(lowered):
    return _tool_call(TOOL_STATUS_POMODORO, {})
```
Place this check **before** `detect_action(prompt)` to avoid "wie lange noch" being misrouted.

### Guard Test Compliance

`tests/runtime/test_contract_guards.py` scans:
- `workers/llm.py`, `workers/stt.py`, `workers/tts.py` — no new workers in this story ✅
- `utterance.py`, `dispatch.py`, `calendar.py`, `ui.py` — no `dict[str, object]` in new signatures ✅

New `_handle_pomodoro_status_query()` signature must be typed:
```python
def _handle_pomodoro_status_query(self, assistant_text: str) -> str:
```
No `dict[str, object]` — compliant ✅

### `from __future__ import annotations` Compliance

All modified Python files already have `from __future__ import annotations` as first non-comment line.
Any new file (`test_pomodoro_session_control.py`) must also include it if it contains type annotations.

### Module Import Order

Follow the project's established import order within each modified file:
1. `from __future__ import annotations`
2. stdlib imports
3. third-party imports
4. local absolute imports (`from contracts.tool_contract import ...`)
5. local relative imports (`from .config import ...`)
6. `TYPE_CHECKING` block (if needed)

### Project Structure Notes

**Files to modify**:
- `src/contracts/tool_contract.py` — Add `TOOL_STATUS_POMODORO` + update sets/tuples
- `src/llm/parser_rules.py` — Add `looks_like_pomodoro_status()`
- `src/llm/fast_path.py` — Import and use `looks_like_pomodoro_status` + `TOOL_STATUS_POMODORO`
- `src/runtime/tools/dispatch.py` — Add case arm + `_handle_pomodoro_status_query()` method
- `src/runtime/tools/messages.py` — Fix idle fallback in `pomodoro_status_message()`

**Files to create**:
- `tests/runtime/test_pomodoro_session_control.py` — Story 3.1 AC coverage tests

**No new worker, protocol, or config changes** — this story touches only tool routing and message logic.

**No changes to `POMODORO_TOOL_TO_RUNTIME_ACTION`** — status is read-only, do not add it there.

**`PomodoroTimer` is instantiated by `_build_runtime_components()` in `engine.py`** — no changes there.

### Alignment with Previous Story Patterns

Story 2.4 retrospective note: all code review findings must be addressed before marking done.
From Epic 1 retro (action #1): `from __future__ import annotations` must be first non-comment line in every `.py` file.

Story 1.4 established `match`/`case` dispatch — this story extends it; never add `if/elif` chains.

Test pattern from `test_tool_dispatch.py` (copy the `_UIServerStub` and `setUp` pattern exactly):
```python
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]
    sys.modules["runtime"] = _pkg

from runtime.tools.dispatch import RuntimeToolDispatcher
from runtime.ui import RuntimeUIPublisher
```

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 3.1 acceptance criteria (FR7, FR8, FR9)
- Project context: `_bmad-output/project-context.md` — Tool system rules, testing patterns, import conventions
- `src/contracts/tool_contract.py` — `TOOL_NAME_ORDER`, `TOOLS_WITHOUT_ARGUMENTS`, `POMODORO_TOOL_NAMES`
- `src/pomodoro/service.py` — `PomodoroTimer.apply()`, `PomodoroTimer.snapshot()`
- `src/pomodoro/constants.py` — `PHASE_*`, `ACTION_*`, `REASON_*` constants
- `src/runtime/tools/dispatch.py` — `RuntimeToolDispatcher.handle_tool_call()` match structure
- `src/runtime/tools/messages.py` — `default_pomodoro_text()`, `pomodoro_rejection_text()`, `pomodoro_status_message()`
- `src/llm/fast_path.py` — `_infer_tool_call()`, existing fast_path routing pattern
- `src/llm/parser_rules.py` — `has_pomodoro_context()`, `detect_action()` patterns
- `tests/runtime/test_tool_dispatch.py` — `_UIServerStub`, `setUp` test pattern to reuse
- `tests/pomodoro/test_timer_characterization.py` — `PomodoroTimer` test pattern with `time.monotonic` patching

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Implemented `TOOL_STATUS_POMODORO = "status_pomodoro_session"` as a read-only query tool; added to `TOOL_NAME_ORDER`, `POMODORO_TOOL_NAMES`, and `TOOLS_WITHOUT_ARGUMENTS` but intentionally NOT to `POMODORO_TOOL_TO_RUNTIME_ACTION`.
- Added `looks_like_pomodoro_status()` to `parser_rules.py`; routes status queries via fast_path BEFORE `detect_action()` to prevent "wie lange noch" from being misrouted.
- `_handle_pomodoro_status_query()` in `dispatch.py` is read-only: calls `pomodoro_status_message(snapshot)`, publishes no UI events.
- Updated `pomodoro_status_message()` idle fallback from `"Bereit"` to `"Keine aktive Pomodoro-Sitzung."` for AC #4 clarity.
- Updated `test_tool_contract_consistency.py` to use `POMODORO_TOOL_NAMES` (covers all 6 pomodoro dispatch paths) instead of `POMODORO_TOOL_TO_RUNTIME_ACTION` (only 5 mutation tools).
- All 174 tests pass; 13 guard tests pass; zero regressions.

### File List

- `src/contracts/tool_contract.py` — added `TOOL_STATUS_POMODORO`, updated `TOOL_NAME_ORDER`, `POMODORO_TOOL_NAMES`, `TOOLS_WITHOUT_ARGUMENTS`
- `src/llm/parser_rules.py` — added `looks_like_pomodoro_status()` (review: removed "noch" from pattern)
- `src/llm/fast_path.py` — imported and wired `looks_like_pomodoro_status` + `TOOL_STATUS_POMODORO`
- `src/llm/parser_messages.py` — added `TOOL_STATUS_POMODORO` handler in `fallback_assistant_text()` (returns `""`)
- `src/runtime/tools/dispatch.py` — added `case _tc.TOOL_STATUS_POMODORO` arm + `_handle_pomodoro_status_query()` method (review: fixed to always use live snapshot)
- `src/runtime/tools/messages.py` — changed `pomodoro_status_message()` idle fallback to `"Keine aktive Pomodoro-Sitzung."`
- `tests/llm/test_fast_path.py` — added status routing tests and "noch" guard tests (review)
- `tests/runtime/test_pomodoro_session_control.py` — new test file (6 tests covering all ACs; review: fixed abort-restart test, added remaining_seconds assertion)
- `tests/runtime/test_tool_contract_consistency.py` — updated coverage check to use `POMODORO_TOOL_NAMES`

## Senior Developer Review (AI)

**Reviewer:** Shrink0r | **Date:** 2026-03-01 | **Outcome:** Changes Requested → Fixed

### Findings Fixed

**[H1] AC #3 BROKEN — status returned "Anfrage verarbeitet." in fast-path scenario**
- Root: `fallback_assistant_text` had no handler for `TOOL_STATUS_POMODORO` → fell through to generic "Anfrage verarbeitet."
- Root: `_handle_pomodoro_status_query` used `assistant_text.strip() or snapshot_message()` — preferred the stale LLM text over live timer data.
- Fix: `_handle_pomodoro_status_query` now always calls `pomodoro_status_message(self._pomodoro_timer.snapshot())` (`assistant_text` unused).
- Fix: `fallback_assistant_text` now returns `""` for `TOOL_STATUS_POMODORO` with a comment explaining why.

**[H2] `looks_like_pomodoro_status` "noch" caused misrouting of common German phrases**
- "Starte die Pomodoro Sitzung noch mal" → was routed to STATUS (short-circuits detect_action).
- Fix: removed `"noch"` from the regex pattern. Status detection still fires on `wie lange`, `verbleibend`, `restzeit`, `wie laeuft`, etc.

**[M1] `tests/llm/test_fast_path.py` not updated**
- No coverage for status routing via fast_path; no guard against "noch mal" misrouting.
- Fix: added 4 tests — status via "wie lange", status via "status" keyword, stop-not-misrouted, noch-mal-not-misrouted.

**[M2] `test_abort_then_restart_begins_fresh_session` bypassed dispatcher for abort step**
- Fix: now uses `dispatcher.handle_tool_call(stop_pomodoro_session)` for the abort, asserting response text too.

**[L1] AC #1 "session start time recorded" not validated in tests**
- Fix: added `assertGreater(snapshot.remaining_seconds, 0)` in `test_start_when_idle_transitions_to_running`.

### Post-Review State
- 178 tests pass (was 174), zero regressions.

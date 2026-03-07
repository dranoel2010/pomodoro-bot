# Story 1.4: Frozen Value Objects & Structural Pattern Matching Dispatch

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want all high-frequency value objects to use `@dataclass(frozen=True, slots=True)` and tool dispatch to use structural pattern matching,
so that per-instance `__dict__` allocation is eliminated on high-frequency IPC construction and adding a new tool requires only one `case` arm addition.

## Acceptance Criteria

1. **Given** the frozen value object migration is complete
   **When** a developer inspects any high-frequency value object (IPC envelopes, metrics payloads, LLM response types)
   **Then** every such type is decorated with `@dataclass(frozen=True, slots=True)`
   **And** no high-frequency value object uses plain `@dataclass` without `slots=True`

2. **Given** the dispatch refactor is complete
   **When** a developer inspects `runtime/tools/dispatch.py`
   **Then** `RuntimeToolDispatcher` uses a `match raw_name:` structural pattern matching statement (where `raw_name` is derived from `tool_call["name"]` and optionally remapped before matching)
   **And** there are no `if/elif` chains in the dispatch path
   **And** each `case` arm calls a single handler function

3. **Given** the dispatch refactor is complete
   **When** a new tool name constant is added to `src/contracts/tool_contract.py`
   **Then** a single `case` arm added to `dispatch.py` is the only required dispatch change — no other file in the dispatch path requires modification

4. **Given** the `ToolName` Literal type is defined in `src/contracts/tool_contract.py`
   **When** `uv run pytest tests/runtime/test_contract_guards.py` is executed
   **Then** all guard tests pass, including enforcement that no `if/elif` dispatch chains exist in guarded paths
   **And** `uv run pytest tests/` passes in full — no regressions introduced

## Tasks / Subtasks

- [x] Confirm all high-frequency value objects are already frozen (AC: #1)
  - [x] Audit: `contracts/ipc.py` (`_RequestEnvelope`, `_ResponseEnvelope`) — already frozen ✅
  - [x] Audit: `llm/types.py` (`EnvironmentContext`) — already frozen ✅
  - [x] Audit: `runtime/workers/llm.py` (`LLMPayload`, `_WorkerConfig`) — already frozen ✅
  - [x] Audit: `runtime/workers/tts.py` (`TTSPayload`, `_WorkerConfig`) — already frozen ✅
  - [x] Audit: `runtime/workers/stt.py` (`_WorkerConfig`) — already frozen ✅
  - [x] Audit: `runtime/workers/core.py` (`_StopSignal`) — already frozen ✅
  - [x] Audit: `stt/events.py` (`Utterance`, `WakeWordDetectedEvent`, `UtteranceCapturedEvent`, `WakeWordErrorEvent`) — already frozen ✅
  - [x] Audit: `pomodoro/service.py` (`PomodoroSnapshot`, `PomodoroActionResult`, `PomodoroTick`) — already frozen ✅
  - [x] Audit: `stt/transcription.py` (`TranscriptionResult`) — already frozen ✅
  - [x] Document any remaining non-frozen value objects and reason (config classes use `replace()` — intentionally mutable)

- [x] Fix `stt/transcription.py` missing `from __future__ import annotations` (AC: #4)
  - [x] Add `from __future__ import annotations` as the first line (before the module docstring or as first import after docstring, matching project convention)
  - [x] Note: this file was renamed from `stt.py` in story 1.3 with no logic changes; the original lacked this import

- [x] Move `ToolName` Literal type from `llm/types.py` to `contracts/tool_contract.py` (AC: #3, #4)
  - [x] In `src/contracts/tool_contract.py`: add `from typing import Literal` and define `ToolName = Literal[*TOOL_NAME_ORDER]` after `TOOL_NAME_ORDER` is defined
  - [x] In `src/llm/types.py`: replace the `ToolName` definition with `from contracts.tool_contract import ToolName` (keep it re-exported for backwards compatibility within the module)
  - [x] In `src/llm/fast_path.py`: update `from .types import StructuredResponse, ToolCall, ToolName` → keep the import from `.types` OR update to import `ToolName` from `contracts.tool_contract` directly (either works since `llm/types.py` will re-export it)
  - [x] Verify no other file imports `ToolName` directly from a non-contracts location

- [x] Refactor `dispatch.py` to use structural pattern matching (AC: #2, #3)
  - [x] Import all 12 individual tool name constants (`TOOL_START_TIMER`, `TOOL_STOP_TIMER`, ..., `TOOL_ADD_CALENDAR_EVENT`) from `contracts.tool_contract` at the top of the file
  - [x] Replace the three `if raw_name in <SET>:` dispatch branches in `handle_tool_call` with a single `match raw_name:` block
  - [x] Pattern: pomodoro tools grouped with `|` operator → calls `_handle_pomodoro_tool_call`
  - [x] Pattern: timer tools grouped with `|` operator → calls `_handle_timer_tool_call`
  - [x] Pattern: calendar tools grouped with `|` operator → calls `handle_calendar_tool_call`
  - [x] Pattern: `case _:` fallthrough → log warning + return `assistant_text`
  - [x] Remove now-unused set membership imports (`CALENDAR_TOOL_NAMES`, `POMODORO_TOOL_TO_RUNTIME_ACTION`, `TIMER_TOOL_TO_RUNTIME_ACTION`) **if** they are no longer needed in `handle_tool_call` (check `_handle_pomodoro_tool_call` and `_handle_timer_tool_call` which still use those dicts internally)
  - [x] Verify `_handle_pomodoro_tool_call` and `_handle_timer_tool_call` still work — they use `POMODORO_TOOL_TO_RUNTIME_ACTION[tool_name]` and `TIMER_TOOL_TO_RUNTIME_ACTION[tool_name]` internally; do NOT remove those imports

- [x] Add `DispatchPatternGuards` class to `tests/runtime/test_contract_guards.py` (AC: #4)
  - [x] Add path constant `_DISPATCH_FILE = _ROOT / "src" / "runtime" / "tools" / "dispatch.py"`
  - [x] Guard 1: `dispatch.py` must contain `match raw_name:` (structural pattern matching is present)
  - [x] Guard 2: `dispatch.py` must not contain `if raw_name in POMODORO_TOOL_TO_RUNTIME_ACTION` (old if-chain routing eliminated)
  - [x] Guard 3: `dispatch.py` must not contain `if raw_name in TIMER_TOOL_TO_RUNTIME_ACTION` (old if-chain routing eliminated)
  - [x] Guard 4: `dispatch.py` must not contain `if raw_name in CALENDAR_TOOL_NAMES` (old if-chain routing eliminated)

- [x] Run full test suite (AC: #4)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — all guard tests pass including new `DispatchPatternGuards`
  - [x] `uv run pytest tests/` — all tests pass, zero regressions

## Dev Notes

### Current State — Exact Violations

#### Violation 1: `dispatch.py` uses `if/elif` chains

```python
# CURRENT — violates architecture mandate for structural pattern matching
def handle_tool_call(self, tool_call: ToolCall, assistant_text: str) -> str:
    raw_name = tool_call["name"]
    normalized_arguments: JSONObject = tool_call.get("arguments", {})

    pomodoro_snapshot = self._pomodoro_timer.snapshot()
    if pomodoro_snapshot.phase in ACTIVE_SESSION_PHASES:
        raw_name = remap_timer_tool_for_active_pomodoro(raw_name, pomodoro_active=True)

    if raw_name in POMODORO_TOOL_TO_RUNTIME_ACTION:          # ← if/elif chain violation
        return self._handle_pomodoro_tool_call(raw_name, normalized_arguments, assistant_text)
    if raw_name in TIMER_TOOL_TO_RUNTIME_ACTION:             # ← if/elif chain violation
        return self._handle_timer_tool_call(raw_name, normalized_arguments, assistant_text)
    if raw_name in CALENDAR_TOOL_NAMES:                      # ← if/elif chain violation
        return handle_calendar_tool_call(...)

    self._logger.warning("Unsupported tool call: %s", raw_name)
    return assistant_text
```

The architecture ADR explicitly forbids `if/elif` chains in the dispatch path. Per the contract:
> `RuntimeToolDispatcher` uses a `match tool_call.name:` structural pattern matching statement

#### Violation 2: `ToolName` Literal in wrong module

```python
# CURRENT — in src/llm/types.py (wrong location)
ToolName = Literal[*TOOL_NAME_ORDER]
```

Architecture specifies `ToolName` lives in `src/contracts/tool_contract.py`. The Literal type is derived from `TOOL_NAME_ORDER` which is already in `tool_contract.py`. Moving it there is a natural co-location.

```python
# CURRENT — consumers import from llm.types
from .types import StructuredResponse, ToolCall, ToolName  # fast_path.py
```

#### Violation 3: `stt/transcription.py` missing `from __future__ import annotations`

```python
# CURRENT — first import is wrong
"""faster-whisper transcription adapters..."""

import logging     # ← from __future__ import annotations is MISSING
from dataclasses import dataclass
```

This file was renamed from `stt/stt.py` in story 1.3 with no logic changes. The original lacked the future import and the rename did not add it. Project rule: every module must begin with `from __future__ import annotations`.

### Target Implementation

#### Fix 1: `contracts/tool_contract.py` — add `ToolName`

```python
# Add after TOOL_NAME_ORDER is defined (near end of existing tuple definition):
from typing import Literal

# ... existing TOOL_NAME_ORDER tuple definition ...

# Canonical ToolName Literal — derived from TOOL_NAME_ORDER for consistency
ToolName = Literal[*TOOL_NAME_ORDER]
```

`TOOL_NAME_ORDER` must be defined before `ToolName = Literal[*TOOL_NAME_ORDER]`.

#### Fix 2: `llm/types.py` — re-export `ToolName` from contracts

```python
# BEFORE
ToolName = Literal[*TOOL_NAME_ORDER]

# AFTER — import from canonical location, re-export for backwards compat
from contracts.tool_contract import ToolName  # noqa: F401 (re-export)
```

Remove the `Literal` import from `llm/types.py` IF it's only used for `ToolName` definition. Check: `EnvironmentContext` in the same file doesn't use `Literal` — only `TypeAlias` and `TypedDict` are needed. So `from typing import Literal, TypeAlias, TypedDict` → `from typing import TypeAlias, TypedDict`.

Actually verify: `ToolName = Literal[*TOOL_NAME_ORDER]` is the only use of `Literal` in `types.py`. If so, remove `Literal` from the import.

#### Fix 3: `dispatch.py` — structural pattern matching

```python
# AFTER — in handle_tool_call()

from contracts.tool_contract import (
    CALENDAR_TOOL_NAMES,               # still needed by _handle_*_tool_call internals
    POMODORO_TOOL_TO_RUNTIME_ACTION,   # still needed by _handle_pomodoro_tool_call
    TIMER_TOOL_TO_RUNTIME_ACTION,      # still needed by _handle_timer_tool_call
    # Add individual tool name constants for match cases:
    TOOL_START_POMODORO,
    TOOL_STOP_POMODORO,
    TOOL_PAUSE_POMODORO,
    TOOL_CONTINUE_POMODORO,
    TOOL_RESET_POMODORO,
    TOOL_START_TIMER,
    TOOL_STOP_TIMER,
    TOOL_PAUSE_TIMER,
    TOOL_CONTINUE_TIMER,
    TOOL_RESET_TIMER,
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_ADD_CALENDAR_EVENT,
)

def handle_tool_call(self, tool_call: ToolCall, assistant_text: str) -> str:
    raw_name = tool_call["name"]
    normalized_arguments: JSONObject = tool_call.get("arguments", {})

    pomodoro_snapshot = self._pomodoro_timer.snapshot()
    if pomodoro_snapshot.phase in ACTIVE_SESSION_PHASES:
        raw_name = remap_timer_tool_for_active_pomodoro(
            raw_name,
            pomodoro_active=True,
        )

    match raw_name:
        case (
            TOOL_START_POMODORO
            | TOOL_STOP_POMODORO
            | TOOL_PAUSE_POMODORO
            | TOOL_CONTINUE_POMODORO
            | TOOL_RESET_POMODORO
        ):
            return self._handle_pomodoro_tool_call(raw_name, normalized_arguments, assistant_text)
        case (
            TOOL_START_TIMER
            | TOOL_STOP_TIMER
            | TOOL_PAUSE_TIMER
            | TOOL_CONTINUE_TIMER
            | TOOL_RESET_TIMER
        ):
            return self._handle_timer_tool_call(raw_name, normalized_arguments, assistant_text)
        case TOOL_SHOW_UPCOMING_EVENTS | TOOL_ADD_CALENDAR_EVENT:
            return handle_calendar_tool_call(
                tool_name=raw_name,
                arguments=normalized_arguments,
                oracle_service=self._oracle_service,
                app_config=self._app_config,
                logger=self._logger,
            )
        case _:
            self._logger.warning("Unsupported tool call: %s", raw_name)
            return assistant_text
```

**Critical constraint**: `_handle_pomodoro_tool_call` and `_handle_timer_tool_call` still use `POMODORO_TOOL_TO_RUNTIME_ACTION[tool_name]` and `TIMER_TOOL_TO_RUNTIME_ACTION[tool_name]` internally. Do NOT remove those imports — the dict lookups inside the private handlers are correct and unchanged.

**How `tell_joke` is added in Story 4.1** (proving the 2-file constraint works):
```python
# dispatch.py — add ONE case arm:
        case TOOL_TELL_JOKE:
            return handle_tell_joke(normalized_arguments, logger=self._logger)
```
Only `tool_contract.py` and `dispatch.py` need changes. ✅

#### Fix 4: New Guard Tests

```python
# Add to tests/runtime/test_contract_guards.py

_DISPATCH_FILE = _ROOT / "src" / "runtime" / "tools" / "dispatch.py"


class DispatchPatternGuards(unittest.TestCase):
    def test_dispatch_uses_structural_pattern_matching(self) -> None:
        source = _DISPATCH_FILE.read_text(encoding="utf-8")
        self.assertIn(
            "match raw_name:",
            source,
            msg="dispatch.py must use 'match raw_name:' structural pattern matching in handle_tool_call",
        )

    def test_dispatch_does_not_use_if_chain_for_pomodoro_tools(self) -> None:
        source = _DISPATCH_FILE.read_text(encoding="utf-8")
        self.assertNotIn(
            "if raw_name in POMODORO_TOOL_TO_RUNTIME_ACTION",
            source,
            msg="dispatch.py must not use if-chain for pomodoro tool routing — use match/case",
        )

    def test_dispatch_does_not_use_if_chain_for_timer_tools(self) -> None:
        source = _DISPATCH_FILE.read_text(encoding="utf-8")
        self.assertNotIn(
            "if raw_name in TIMER_TOOL_TO_RUNTIME_ACTION",
            source,
            msg="dispatch.py must not use if-chain for timer tool routing — use match/case",
        )

    def test_dispatch_does_not_use_if_chain_for_calendar_tools(self) -> None:
        source = _DISPATCH_FILE.read_text(encoding="utf-8")
        self.assertNotIn(
            "if raw_name in CALENDAR_TOOL_NAMES",
            source,
            msg="dispatch.py must not use if-chain for calendar tool routing — use match/case",
        )
```

### Frozen Value Objects — Complete Audit (Story 1.4)

**Already compliant — no changes needed:**

| Type | Location | Status |
|---|---|---|
| `_RequestEnvelope` | `contracts/ipc.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `_ResponseEnvelope` | `contracts/ipc.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `EnvironmentContext` | `llm/types.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `LLMPayload` | `runtime/workers/llm.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `_WorkerConfig` (LLM) | `runtime/workers/llm.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `TTSPayload` | `runtime/workers/tts.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `_WorkerConfig` (TTS) | `runtime/workers/tts.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `_WorkerConfig` (STT) | `runtime/workers/stt.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `_StopSignal` | `runtime/workers/core.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `TranscriptionResult` | `stt/transcription.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `Utterance` | `stt/events.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `WakeWordDetectedEvent` | `stt/events.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `UtteranceCapturedEvent` | `stt/events.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `WakeWordErrorEvent` | `stt/events.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `PomodoroSnapshot` | `pomodoro/service.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `PomodoroActionResult` | `pomodoro/service.py` | `@dataclass(frozen=True, slots=True)` ✅ |
| `PomodoroTick` | `pomodoro/service.py` | `@dataclass(frozen=True, slots=True)` ✅ |

**Intentionally NOT frozen (correct design):**
- `LLMConfig` — uses `dataclasses.replace()` in `workers/llm.py` for thread adjustment; mutable config holder
- `AppConfig`, `*Settings` in `app_config_schema.py` — config holders, not value objects
- `STTConfig`, `TTSConfig`, `WakeWordConfig` — config holders

**TypedDicts (not dataclasses, correct design):**
- `StructuredResponse`, `ToolCall` in `llm/types.py` — TypedDict schema, correct for LLM output contract

The frozen value objects AC is **already satisfied**. No dataclass changes are needed for AC #1 — the primary work of story 1.4 is the dispatch refactor and `ToolName` move.

### `ToolName` Import Chain After Move

```
contracts/tool_contract.py     → defines ToolName = Literal[*TOOL_NAME_ORDER]
llm/types.py                   → imports ToolName from contracts.tool_contract (re-exports)
llm/fast_path.py               → from .types import StructuredResponse, ToolCall, ToolName  (unchanged)
```

The `dispatch.py` file doesn't directly import `ToolName` — it uses `ToolCall` which is a TypedDict with a `name: ToolName` field. No change needed in dispatch imports for `ToolName` itself.

### Test Impact Analysis

- **`tests/runtime/test_contract_guards.py`**: Add `DispatchPatternGuards` class with 4 new tests. No existing tests modified.
- **All existing dispatch tests**: The `_handle_pomodoro_tool_call`, `_handle_timer_tool_call`, and `handle_calendar_tool_call` logic is unchanged — only the top-level routing changes from `if` chains to `match`. Existing behavioural tests should continue to pass.
- **`tests/llm/test_fast_path.py`**: If `ToolName` import path changes in `fast_path.py`, the patch targets may need updating. But if `fast_path.py` still imports `ToolName` from `.types` (which re-exports it), no test changes are needed.
- **Expected final test count**: 149 + 4 = 153 tests, or 149 + 4 = 153 (if no existing tests break).

### Architecture Compliance Checklist

- `from __future__ import annotations` must be first code line in ALL modified files (including `stt/transcription.py` fix)
- `ToolName` must be defined in `contracts/tool_contract.py` — not in `llm/types.py`
- `match raw_name:` statement is inside `handle_tool_call` after the optional remap step
- Private handler methods `_handle_pomodoro_tool_call` and `_handle_timer_tool_call` are **not** affected — only the routing in `handle_tool_call` changes
- New guard tests must follow `unittest.TestCase` base class pattern
- Run `uv run pytest tests/runtime/test_contract_guards.py` after every structural change before the full suite
- This is Step 6 of 8 in Phase 1. Follows Story 1.3 (LLM module boundaries — done). Precedes 1.5 (hardware-free test suite verification).

### Project Structure Notes

- `src/` is on `sys.path` — all cross-package imports use module name directly without `src.` prefix
- `contracts/tool_contract.py` imports from `pomodoro.constants` (for `ACTION_*`) — `from typing import Literal` is a stdlib addition, no new dependency
- `dispatch.py` already imports from `contracts.tool_contract` — adding individual tool name constants is an additive change to the existing import block
- Python 3.13+ `match`/`case` with `|` pattern syntax is in active use in the project — no version concerns
- The `match raw_name:` construct uses `raw_name` (post-remap string) not `tool_call.name` directly — this is correct since `remap_timer_tool_for_active_pomodoro` may have changed the name

### References

- Epics file: `_bmad-output/planning-artifacts/epics.md` — Story 1.4 acceptance criteria
- Architecture ADR: `_bmad-output/planning-artifacts/architecture.md` — "Contracts & Interface Architecture" section (ToolName in tool_contract.py), "Communication Patterns" section (match statement example), "Implementation Patterns" section (dispatch tool addition checklist)
- Project context: `_bmad-output/project-context.md` — Rule 1 (import style), Rule 7 (dataclass style), Tool System section (TOOLS_WITHOUT_ARGUMENTS), Framework/Architecture Rules section
- Story 1.3 dev notes: explicitly deferred this story's work ("Do NOT add `@dataclass(frozen=True, slots=True)` to anything in this story — that is Story 1.4's scope", "Do NOT modify dispatch logic or tool contract — not in scope")
- `src/runtime/tools/dispatch.py` — primary change target (match statement refactor)
- `src/contracts/tool_contract.py` — add `ToolName` Literal type
- `src/llm/types.py` — change `ToolName` from definition to import
- `src/stt/transcription.py` — add `from __future__ import annotations`
- `tests/runtime/test_contract_guards.py` — add `DispatchPatternGuards` class
- Implementation sequence note: Step 6 of 8 in Phase 1. Previous story 1-3 is done. Next is 1-5 (hardware-free test suite verification).

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

Python `match/case` with plain imported constants treats them as capture variables (not value patterns). Fixed by using `import contracts.tool_contract as _tc` (module alias) so case arms use dotted names (`_tc.TOOL_START_POMODORO`) which Python recognises as value patterns.

### Completion Notes List

- AC #1: All 17 high-frequency value objects audited — confirmed already `@dataclass(frozen=True, slots=True)`. No dataclass changes needed.
- AC #4 (transcription.py): Added `from __future__ import annotations` as first import in `src/stt/transcription.py` (file was renamed from `stt.py` in story 1.3 without adding the future import).
- AC #3/#4 (ToolName move): `ToolName = Literal[*TOOL_NAME_ORDER]` moved to `src/contracts/tool_contract.py` (canonical location). `src/llm/types.py` now re-exports it via `from contracts.tool_contract import ToolName  # noqa: F401`. Removed `Literal` and `TOOL_NAME_ORDER` imports from `llm/types.py` as they were only used for the now-moved definition.
- AC #2/#3 (dispatch refactor): `handle_tool_call` in `src/runtime/tools/dispatch.py` refactored from three `if raw_name in <SET>:` chains to a single `match raw_name:` structural pattern matching block using module-alias dotted names (`_tc.TOOL_*`). `CALENDAR_TOOL_NAMES` import removed (no longer used after refactor). `POMODORO_TOOL_TO_RUNTIME_ACTION` and `TIMER_TOOL_TO_RUNTIME_ACTION` retained (still used by private handler methods).
- AC #4 (guard tests): Added `DispatchPatternGuards` class with 4 tests to `tests/runtime/test_contract_guards.py`. Guards enforce `match raw_name:` present and all three `if raw_name in <SET>:` patterns absent.
- Additional cleanup (applied alongside story work): Removed superfluous `now_fn` lambda from `src/llm/fast_path.py` calendar branch (functionally equivalent; extractor defaults to `datetime.now().astimezone()`). Added `from __future__ import annotations` to `tests/llm/test_fast_path.py`, `tests/runtime/test_ticks_state_flow.py`, `tests/runtime/test_utterance_state_flow.py`, `tests/stt/test_stt_download_root.py`. Replaced hard-coded `"replying"`/`"assistant_reply"` string literals with `STATE_REPLYING`/`EVENT_ASSISTANT_REPLY` constants in tick and utterance test files. Fixed patch target in `test_stt_download_root.py`: `stt.transcription.WhisperModel` → `faster_whisper.WhisperModel` (correct patch point for a module-scoped import inside a method). Added `test_process_utterance_fast_path_bypasses_llm` to `tests/runtime/test_utterance_state_flow.py`.
- Full test suite: 154/154 passed (149 pre-existing + 5 new). Zero regressions.

### File List

- `src/stt/transcription.py` — added `from __future__ import annotations`
- `src/contracts/tool_contract.py` — added `from typing import Literal`; added `ToolName = Literal[*TOOL_NAME_ORDER]`
- `src/llm/types.py` — replaced `ToolName` definition with re-export import; removed `Literal` and `TOOL_NAME_ORDER` from imports; added blank line separator between import block and TypeAlias definitions
- `src/llm/fast_path.py` — removed superfluous `now_fn` lambda and `from datetime import datetime` import from calendar branch (functionally equivalent; extractor defaults internally)
- `src/runtime/tools/dispatch.py` — added `import contracts.tool_contract as _tc`; removed `CALENDAR_TOOL_NAMES` import; replaced `if/elif` chain with `match raw_name:` structural pattern matching
- `tests/runtime/test_contract_guards.py` — added `DispatchPatternGuards` class with 4 guard tests; added `_DISPATCH_FILE` path constant
- `tests/llm/test_fast_path.py` — added `from __future__ import annotations`
- `tests/runtime/test_ticks_state_flow.py` — added `from __future__ import annotations`; imported `EVENT_ASSISTANT_REPLY, STATE_REPLYING` from `contracts.ui_protocol`; replaced hard-coded string literals with constants
- `tests/runtime/test_utterance_state_flow.py` — added `from __future__ import annotations`; imported `EVENT_ASSISTANT_REPLY, STATE_REPLYING` from `contracts.ui_protocol`; replaced hard-coded string literals with constants; added `run_call_count` to LLM stub; added `test_process_utterance_fast_path_bypasses_llm`
- `tests/stt/test_stt_download_root.py` — added `from __future__ import annotations`; fixed mock patch target from `stt.transcription.WhisperModel` to `faster_whisper.WhisperModel`

## Change Log

- 2026-02-28: Story 1-4 implemented — frozen value objects audit (all compliant), `from __future__ import annotations` fix in `stt/transcription.py`, `ToolName` moved to `contracts/tool_contract.py`, `dispatch.py` refactored to use `match raw_name:` structural pattern matching, `DispatchPatternGuards` tests added (153/153 tests pass)

# Story 4.1: Pure-LLM Tool — `tell_joke`

Status: done

## Story

As a developer,
I want to add a `tell_joke` tool by modifying exactly 2 source files,
so that the ≤2-file tool-addition contract established in Epic 1 is proved with a real working tool.

## Acceptance Criteria

1. **Given** the contracts and dispatch architecture from Epic 1 is stable
   **When** the `tell_joke` tool is implemented
   **Then** exactly 2 source files are modified for the tool to **function via LLM dispatch**: `src/contracts/tool_contract.py` and `src/runtime/tools/dispatch.py`
   **And** no other source file requires modification for the tool to be callable via LLM inference

2. **Given** `src/contracts/tool_contract.py` is updated
   **When** a developer inspects the file
   **Then** a `TOOL_TELL_JOKE = "tell_joke"` constant is defined
   **And** `"tell_joke"` is appended to `TOOL_NAME_ORDER` at the correct position (after `TOOL_STATUS_POMODORO`, before `TOOL_SHOW_UPCOMING_EVENTS`)
   **And** `TOOL_TELL_JOKE` is added to `TOOLS_WITHOUT_ARGUMENTS` — the tool takes no arguments; omitting this causes malformed GBNF grammar

3. **Given** `src/runtime/tools/dispatch.py` is updated
   **When** a developer inspects the `match raw_name:` statement in `handle_tool_call()`
   **Then** a single `case _tc.TOOL_TELL_JOKE:` arm exists that calls a `_handle_tell_joke` handler
   **And** `_handle_tell_joke` is a module-level function (not a method) that returns a German joke as the response string
   **And** no external dependency, oracle call, or subprocess spawn is required by the handler

4. **Given** `tell_joke` is dispatched
   **When** the user says the German trigger phrase (e.g. "Erzähl mir einen Witz")
   **Then** the fast-path in `llm/fast_path.py` routes the deterministic phrase directly — no LLM inference required
   **And** TTS speaks the German joke response
   **And** `PipelineMetrics` reflects `llm_ms: 0` and `tokens: 0` for the fast-path route
   **Note:** This AC requires additional changes to `parser_rules.py` and `fast_path.py` beyond the 2-file minimum. This does NOT invalidate AC 1 — the tool functions via LLM dispatch with exactly 2 files; fast-path is an optimisation, not a requirement for function.

5. **Given** `tell_joke` is implemented
   **When** `uv run pytest tests/` is executed
   **Then** all tests pass including a new unit test for `_handle_tell_joke` that requires no model files or subprocesses
   **And** the 205 existing tests pass without regressions

## Tasks / Subtasks

- [x] Modify `src/contracts/tool_contract.py` (AC: #1, #2)
  - [x] Add `TOOL_TELL_JOKE = "tell_joke"` constant after `TOOL_STATUS_POMODORO`
  - [x] Append `TOOL_TELL_JOKE` to `TOOL_NAME_ORDER` tuple (after `TOOL_STATUS_POMODORO`, before `TOOL_SHOW_UPCOMING_EVENTS`)
  - [x] Add `TOOL_TELL_JOKE` to `TOOLS_WITHOUT_ARGUMENTS` frozenset — CRITICAL: omitting causes malformed LLM GBNF grammar
  - [x] Add `PURE_LLM_TOOL_NAMES: frozenset[str] = frozenset({TOOL_TELL_JOKE})` — CRITICAL: required to fix `test_tool_contract_consistency.py` (see Dev Notes)

- [x] Modify `src/runtime/tools/dispatch.py` (AC: #1, #3)
  - [x] Add module-level function `_handle_tell_joke(assistant_text: str) -> str` that returns a German joke (`del assistant_text` — joke is hardcoded)
  - [x] Add `case _tc.TOOL_TELL_JOKE: return _handle_tell_joke(assistant_text)` arm in `handle_tool_call()` — place before the `case _:` fallback arm
  - [x] No new imports needed (`_tc.TOOL_TELL_JOKE` is accessible via existing `import contracts.tool_contract as _tc`)

- [x] Modify `src/llm/parser_rules.py` for fast-path (AC: #4)
  - [x] Add `looks_like_tell_joke(lowered_prompt: str) -> bool` function detecting German joke request keywords (`witz`, `witze`, `scherz`, `lustig`, `erzähl mir einen`)

- [x] Modify `src/llm/fast_path.py` for fast-path routing (AC: #4)
  - [x] Import `TOOL_TELL_JOKE` from `contracts.tool_contract`
  - [x] Import `looks_like_tell_joke` from `.parser_rules`
  - [x] Add `if looks_like_tell_joke(lowered): return _tool_call(TOOL_TELL_JOKE, {})` check **early** in `_infer_tool_call()` — before action detection, as joke requests have no action keyword

- [x] Update `tests/runtime/test_tool_contract_consistency.py` — REQUIRED to fix a regression (AC: #5)
  - [x] Import `PURE_LLM_TOOL_NAMES` in the existing import block
  - [x] In `test_runtime_dispatch_and_calendar_cover_all_tools`, add `| PURE_LLM_TOOL_NAMES` to the `covered` set — without this, the test FAILS after adding `TOOL_TELL_JOKE` to `TOOL_NAMES`

- [x] Write `tests/runtime/test_tell_joke.py` (AC: #5)
  - [x] Test: **`handle_tool_call({"name": "tell_joke", ...}, "")` returns a non-empty German string** (via `RuntimeToolDispatcher` — same import pattern as `test_pomodoro_session_control.py`)
  - [x] Test: **`TOOL_TELL_JOKE` is in `TOOL_NAME_ORDER`** (contract guard)
  - [x] Test: **`TOOL_TELL_JOKE` is in `TOOLS_WITHOUT_ARGUMENTS`** (contract guard)
  - [x] Test: **`TOOL_TELL_JOKE` is in `PURE_LLM_TOOL_NAMES`** (new frozenset guard)
  - [x] Test: **fast-path routes "Erzähl mir einen Witz" to `tell_joke`** (via `maybe_fast_path_response`)
  - [x] Test: **fast-path does NOT route "Starte einen Timer für 10 Minuten" to `tell_joke`**

- [x] Run full test suite (AC: #5)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — guard tests pass
  - [x] `uv run pytest tests/runtime/test_tool_contract_consistency.py` — consistency test passes with new coverage
  - [x] `uv run pytest tests/runtime/test_tell_joke.py` — all new tests pass
  - [x] `uv run pytest tests/` — all tests pass (205 existing + 13 new = 218 total)

## Dev Notes

### Architecture Compliance: 2-File Tool Addition Pattern

**This story exists specifically to prove NFR-M1**: *"Adding a new tool call that requires no external oracle dependency must require changes to at most 2 source files."*

The 2 source files are:
1. `src/contracts/tool_contract.py` — the single source of truth for all tool names
2. `src/runtime/tools/dispatch.py` — where the handler lives

Everything else in the pipeline picks up the new tool automatically:
- `ToolName` Literal type (in `llm/types.py`) is derived from `TOOL_NAME_ORDER` — no change needed
- LLM GBNF grammar alternatives are generated from `TOOL_NAME_ORDER` via `tool_name_gbnf_alternatives()` — no change needed
- Prompt CSV `tool_names_one_of_csv()` auto-updates — no change needed

**The fast-path changes (AC 4) are ADDITIONAL**, not required for tool function. The story tasks for `parser_rules.py` and `fast_path.py` are performed after the 2-file core is working.

### `src/contracts/tool_contract.py` — Exact Changes

Add the constant after `TOOL_STATUS_POMODORO`:
```python
TOOL_STATUS_POMODORO = "status_pomodoro_session"
TOOL_TELL_JOKE = "tell_joke"          # NEW
```

Update `TOOL_NAME_ORDER` (insert at position 11, before `TOOL_SHOW_UPCOMING_EVENTS`):
```python
TOOL_NAME_ORDER: tuple[str, ...] = (
    TOOL_START_TIMER,
    TOOL_STOP_TIMER,
    TOOL_PAUSE_TIMER,
    TOOL_CONTINUE_TIMER,
    TOOL_RESET_TIMER,
    TOOL_START_POMODORO,
    TOOL_STOP_POMODORO,
    TOOL_PAUSE_POMODORO,
    TOOL_CONTINUE_POMODORO,
    TOOL_RESET_POMODORO,
    TOOL_STATUS_POMODORO,
    TOOL_TELL_JOKE,          # NEW
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_ADD_CALENDAR_EVENT,
)
```

Update `TOOLS_WITHOUT_ARGUMENTS` (add `TOOL_TELL_JOKE`):
```python
TOOLS_WITHOUT_ARGUMENTS: frozenset[str] = frozenset(
    {
        TOOL_STOP_TIMER,
        TOOL_PAUSE_TIMER,
        TOOL_CONTINUE_TIMER,
        TOOL_RESET_TIMER,
        TOOL_STOP_POMODORO,
        TOOL_PAUSE_POMODORO,
        TOOL_CONTINUE_POMODORO,
        TOOL_RESET_POMODORO,
        TOOL_STATUS_POMODORO,
        TOOL_TELL_JOKE,      # NEW — no arguments; omitting this breaks GBNF grammar generation
    }
)
```

Add a new `PURE_LLM_TOOL_NAMES` frozenset for tools that need no runtime action mapping (pure LLM dispatch only):

```python
PURE_LLM_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_TELL_JOKE,  # no arguments, no external deps, dispatched to hardcoded handler
    }
)
```

**Do NOT** add `TOOL_TELL_JOKE` to `TIMER_TOOL_NAMES`, `POMODORO_TOOL_NAMES`, or `CALENDAR_TOOL_NAMES` — it belongs to none of them.

**CRITICAL: `test_tool_contract_consistency.py` will FAIL without `PURE_LLM_TOOL_NAMES`**

The existing `test_runtime_dispatch_and_calendar_cover_all_tools` test asserts:
```python
covered = (
    set(TIMER_TOOL_TO_RUNTIME_ACTION)
    | POMODORO_TOOL_NAMES
    | set(CALENDAR_TOOL_NAMES)
)
self.assertEqual(set(TOOL_NAMES), covered)
```
Adding `TOOL_TELL_JOKE` to `TOOL_NAMES` (via `TOOL_NAME_ORDER`) makes `set(TOOL_NAMES) != covered` — the test FAILS. Fix: add `| PURE_LLM_TOOL_NAMES` to `covered` in that test. See the Tasks section for the exact change.

### `src/runtime/tools/dispatch.py` — Exact Changes

Add a module-level handler function BEFORE the `RuntimeToolDispatcher` class definition (following the convention of having helpers before classes):

```python
def _handle_tell_joke(assistant_text: str) -> str:
    del assistant_text  # joke is hardcoded; LLM text is irrelevant
    return (
        "Warum können Geister so schlecht lügen? "
        "Weil man durch sie hindurchsehen kann."
    )
```

In `handle_tool_call()`, add the new `case` arm before `case _:`:

```python
match raw_name:
    case _tc.TOOL_STATUS_POMODORO:
        return self._handle_pomodoro_status_query(assistant_text)
    case (
        _tc.TOOL_START_POMODORO
        | _tc.TOOL_STOP_POMODORO
        | _tc.TOOL_PAUSE_POMODORO
        | _tc.TOOL_CONTINUE_POMODORO
        | _tc.TOOL_RESET_POMODORO
    ):
        return self._handle_pomodoro_tool_call(raw_name, normalized_arguments, assistant_text)
    case (
        _tc.TOOL_START_TIMER
        | _tc.TOOL_STOP_TIMER
        | _tc.TOOL_PAUSE_TIMER
        | _tc.TOOL_CONTINUE_TIMER
        | _tc.TOOL_RESET_TIMER
    ):
        return self._handle_timer_tool_call(raw_name, normalized_arguments, assistant_text)
    case _tc.TOOL_SHOW_UPCOMING_EVENTS | _tc.TOOL_ADD_CALENDAR_EVENT:
        return handle_calendar_tool_call(
            tool_name=raw_name,
            arguments=normalized_arguments,
            oracle_service=self._oracle_service,
            app_config=self._app_config,
            logger=self._logger,
        )
    case _tc.TOOL_TELL_JOKE:             # NEW
        return _handle_tell_joke(assistant_text)  # NEW
    case _:
        self._logger.warning("Unsupported tool call: %s", raw_name)
        return assistant_text
```

**No new imports required** — `_tc.TOOL_TELL_JOKE` is accessible via the existing `import contracts.tool_contract as _tc` alias.

**Contract guard safety** — `dict[str, object]` guard in `test_contract_guards.py` scans `dispatch.py` for the pattern. `_handle_tell_joke` takes `str` → returns `str`, no dicts. Guard safe.

### `src/llm/parser_rules.py` — Fast-Path Addition

Add `looks_like_tell_joke()` function at the end of the file:

```python
def looks_like_tell_joke(lowered_prompt: str) -> bool:
    """Return whether text looks like a request for a joke."""
    return bool(re.search(
        r"\b(witz|witze|scherz|joke|erzähl mir einen|erzaehl mir einen|lustig)\b",
        lowered_prompt,
    ))
```

The regex captures both umlaut (ä) and umlaut-free (ae) spellings of "erzähl". `re` is already imported.

### `src/llm/fast_path.py` — Fast-Path Routing Addition

Add `TOOL_TELL_JOKE` to the imports from `contracts.tool_contract`:

```python
from contracts.tool_contract import (
    INTENT_TO_POMODORO_TOOL,
    INTENT_TO_TIMER_TOOL,
    TOOL_ADD_CALENDAR_EVENT,
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_START_POMODORO,
    TOOL_START_TIMER,
    TOOL_STATUS_POMODORO,
    TOOL_TELL_JOKE,          # NEW
    TOOLS_WITHOUT_ARGUMENTS,
)
```

Add `looks_like_tell_joke` to the `parser_rules` import:

```python
from .parser_rules import (
    detect_action,
    has_pomodoro_context,
    has_timer_context,
    looks_like_add_calendar,
    looks_like_pomodoro_status,
    looks_like_show_events,
    looks_like_tell_joke,    # NEW
)
```

In `_infer_tool_call()`, add the joke detection **before** the `looks_like_add_calendar` check (it has no action keyword, so it must be detected before action-based routing):

```python
def _infer_tool_call(prompt: str) -> ToolCall | None:
    """Stateless deterministic intent → ToolCall mapping."""
    lowered = prompt.lower()

    if looks_like_tell_joke(lowered):          # NEW — before action detection
        return _tool_call(TOOL_TELL_JOKE, {})  # NEW

    if looks_like_add_calendar(lowered):
        ...
```

### `tests/runtime/test_tool_contract_consistency.py` — Required Fix

Update the existing import and the `test_runtime_dispatch_and_calendar_cover_all_tools` test:

```python
# ADD to existing import block:
from contracts.tool_contract import (
    CALENDAR_TOOL_NAMES,
    INTENT_TO_POMODORO_TOOL,
    INTENT_TO_TIMER_TOOL,
    POMODORO_TOOL_NAMES,
    POMODORO_TOOL_TO_RUNTIME_ACTION,
    PURE_LLM_TOOL_NAMES,          # NEW
    TIMER_TOOL_TO_RUNTIME_ACTION,
    TOOL_NAME_ORDER,
    TOOL_NAMES,
    tool_name_gbnf_alternatives,
    tool_names_one_of_csv,
)

# UPDATE the test body:
def test_runtime_dispatch_and_calendar_cover_all_tools(self) -> None:
    covered = (
        set(TIMER_TOOL_TO_RUNTIME_ACTION)
        | POMODORO_TOOL_NAMES
        | set(CALENDAR_TOOL_NAMES)
        | PURE_LLM_TOOL_NAMES      # NEW
    )
    self.assertEqual(set(TOOL_NAMES), covered)
```

This is the ONLY change to this file. All other tests in it pass unchanged.

### `parser_messages.py` — Optional Enhancement (NOT Required)

`fallback_assistant_text()` in `parser_messages.py` will return `"Anfrage verarbeitet."` for `tell_joke` (hitting the default branch). This placeholder text is **never spoken to the user** because `_handle_tell_joke` in dispatch always replaces it with the real joke. Therefore, no change to `parser_messages.py` is required.

If a developer wants completeness, they can optionally add:
```python
if name == TOOL_TELL_JOKE:
    return "Warum können Geister so schlecht lügen? Weil man durch sie hindurchsehen kann."
```
But this is NOT part of the 2-file tool addition contract and NOT required for AC compliance.

### Test File Structure: `tests/runtime/test_tell_joke.py`

**Import pattern**: Follow `tests/runtime/test_pomodoro_session_control.py` exactly — it already handles all transitive imports for `dispatch.py` without additional stubs. Oracle and app_config imports in `dispatch.py` are in `TYPE_CHECKING` blocks only (runtime-safe).

```python
from __future__ import annotations

import logging
import sys
import types
import unittest
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from pomodoro import PomodoroTimer

# Inject runtime package without triggering __init__.py (avoids pulling in RuntimeEngine)
_RUNTIME_DIR = _SRC_DIR / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg

from runtime.tools.dispatch import RuntimeToolDispatcher
from runtime.ui import RuntimeUIPublisher

# Inject llm package for fast-path tests
_LLM_DIR = _SRC_DIR / "llm"
if "llm" not in sys.modules:
    _llm_pkg = types.ModuleType("llm")
    _llm_pkg.__path__ = [str(_LLM_DIR)]  # type: ignore[attr-defined]
    sys.modules["llm"] = _llm_pkg

from llm.fast_path import maybe_fast_path_response


class _UIServerStub:
    def __init__(self):
        self.events: list[tuple[str, dict[str, object]]] = []
        self.states: list[tuple[str, str | None, dict[str, object]]] = []

    def publish(self, event_type: str, **payload):
        self.events.append((event_type, payload))

    def publish_state(self, state: str, *, message=None, **payload):
        self.states.append((state, message, payload))


class _OracleSettingsStub:
    google_calendar_max_results = 3


class _AppConfigStub:
    oracle = _OracleSettingsStub()


class TellJokeDispatchTests(unittest.TestCase):
    """Verify tell_joke tool dispatch via RuntimeToolDispatcher."""

    def setUp(self) -> None:
        self.ui_server = _UIServerStub()
        self.ui = RuntimeUIPublisher(self.ui_server)
        self.dispatcher = RuntimeToolDispatcher(
            logger=logging.getLogger("test"),
            app_config=_AppConfigStub(),
            oracle_service=None,
            pomodoro_timer=PomodoroTimer(duration_seconds=25 * 60),
            countdown_timer=PomodoroTimer(duration_seconds=10 * 60),
            ui=self.ui,
        )

    def test_tell_joke_returns_non_empty_string(self) -> None:
        result = self.dispatcher.handle_tool_call(
            {"name": "tell_joke", "arguments": {}}, ""
        )
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 10)

    def test_tell_joke_response_is_deterministic(self) -> None:
        r1 = self.dispatcher.handle_tool_call({"name": "tell_joke", "arguments": {}}, "")
        r2 = self.dispatcher.handle_tool_call({"name": "tell_joke", "arguments": {}}, "anything")
        self.assertEqual(r1, r2)

    def test_tell_joke_ignores_assistant_text(self) -> None:
        result = self.dispatcher.handle_tool_call(
            {"name": "tell_joke", "arguments": {}}, "some LLM text"
        )
        # The handler ignores assistant_text — result should be the hardcoded joke
        self.assertNotEqual("some LLM text", result)


class ToolContractGuardTests(unittest.TestCase):
    """Verify TOOL_TELL_JOKE contract compliance."""

    def test_tool_tell_joke_in_tool_name_order(self) -> None:
        from contracts.tool_contract import TOOL_NAME_ORDER, TOOL_TELL_JOKE
        self.assertIn(TOOL_TELL_JOKE, TOOL_NAME_ORDER)

    def test_tool_tell_joke_in_tools_without_arguments(self) -> None:
        from contracts.tool_contract import TOOLS_WITHOUT_ARGUMENTS, TOOL_TELL_JOKE
        self.assertIn(
            TOOL_TELL_JOKE,
            TOOLS_WITHOUT_ARGUMENTS,
            "TOOL_TELL_JOKE must be in TOOLS_WITHOUT_ARGUMENTS — omitting breaks GBNF grammar",
        )

    def test_tool_tell_joke_in_pure_llm_tool_names(self) -> None:
        from contracts.tool_contract import PURE_LLM_TOOL_NAMES, TOOL_TELL_JOKE
        self.assertIn(TOOL_TELL_JOKE, PURE_LLM_TOOL_NAMES)

    def test_tool_tell_joke_not_in_timer_tool_names(self) -> None:
        from contracts.tool_contract import TIMER_TOOL_NAMES, TOOL_TELL_JOKE
        self.assertNotIn(TOOL_TELL_JOKE, TIMER_TOOL_NAMES)

    def test_tool_tell_joke_not_in_pomodoro_tool_names(self) -> None:
        from contracts.tool_contract import POMODORO_TOOL_NAMES, TOOL_TELL_JOKE
        self.assertNotIn(TOOL_TELL_JOKE, POMODORO_TOOL_NAMES)

    def test_tool_tell_joke_not_in_calendar_tool_names(self) -> None:
        from contracts.tool_contract import CALENDAR_TOOL_NAMES, TOOL_TELL_JOKE
        self.assertNotIn(TOOL_TELL_JOKE, CALENDAR_TOOL_NAMES)


class FastPathTellJokeTests(unittest.TestCase):
    """Tests for fast-path routing of tell_joke."""

    def test_fast_path_routes_erzaehl_mir_einen_witz(self) -> None:
        result = maybe_fast_path_response("Erzähl mir einen Witz")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path to route joke request")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("tell_joke", tool_call["name"])
        self.assertEqual({}, tool_call["arguments"])

    def test_fast_path_routes_witz_keyword(self) -> None:
        result = maybe_fast_path_response("Hast du einen guten Witz für mich?")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected fast-path to route joke request")
        tool_call = result["tool_call"]
        self.assertIsNotNone(tool_call)
        if tool_call is None:
            self.fail("Expected tool_call")
        self.assertEqual("tell_joke", tool_call["name"])

    def test_fast_path_timer_not_misrouted_as_tell_joke(self) -> None:
        result = maybe_fast_path_response("Starte einen Timer für 10 Minuten")
        tool_call = result["tool_call"] if result else None
        if tool_call:
            self.assertNotEqual("tell_joke", tool_call["name"])

    def test_fast_path_tell_joke_has_no_arguments(self) -> None:
        result = maybe_fast_path_response("Erzähl mir einen Witz")
        self.assertIsNotNone(result)
        tool_call = result["tool_call"] if result else None
        self.assertIsNotNone(tool_call)
        if tool_call:
            self.assertEqual({}, tool_call["arguments"])


if __name__ == "__main__":
    unittest.main()
```

### Data Flow: tell_joke Tool

**Via LLM (standard path):**
```
User: "Erzähl mir was Witziges"
  ↓
fast_path: looks_like_tell_joke → False (no exact keyword)
  ↓ [falls through to LLM]
LLM: {"assistant_text": "...", "tool_call": {"name": "tell_joke", "arguments": {}}}
  ↓
dispatch case _tc.TOOL_TELL_JOKE: → _handle_tell_joke("...")
  ↓
TTS: "Warum können Geister so schlecht lügen? Weil man durch sie hindurchsehen kann."
  ↓
PipelineMetrics: llm_ms > 0, tokens > 0 (LLM was called)
```

**Via fast-path (optimised path):**
```
User: "Erzähl mir einen Witz"
  ↓
fast_path: looks_like_tell_joke("erzähl mir einen witz") → True
  ↓
Returns: {"assistant_text": "Anfrage verarbeitet.", "tool_call": {"name": "tell_joke", ...}}
  ↓
dispatch case _tc.TOOL_TELL_JOKE: → _handle_tell_joke("Anfrage verarbeitet.")
  → del assistant_text; return joke
  ↓
TTS: "Warum können Geister so schlecht lügen? Weil man durch sie hindurchsehen kann."
  ↓
PipelineMetrics: llm_ms: 0, tokens: 0 (fast-path bypassed LLM)
```

### Project Structure Notes

**Files to modify:**
- `src/contracts/tool_contract.py` — add `TOOL_TELL_JOKE`, add to `TOOL_NAME_ORDER`, `TOOLS_WITHOUT_ARGUMENTS`, and new `PURE_LLM_TOOL_NAMES`
- `src/runtime/tools/dispatch.py` — add `_handle_tell_joke()` module-level function + `case _tc.TOOL_TELL_JOKE:` arm
- `src/llm/parser_rules.py` — add `looks_like_tell_joke()` function (fast-path detection)
- `src/llm/fast_path.py` — import `TOOL_TELL_JOKE` + `looks_like_tell_joke`, add check in `_infer_tool_call()`
- `tests/runtime/test_tool_contract_consistency.py` — import `PURE_LLM_TOOL_NAMES`, add `| PURE_LLM_TOOL_NAMES` to `covered` set in `test_runtime_dispatch_and_calendar_cover_all_tools` **REQUIRED to prevent test failure**

**File to create:**
- `tests/runtime/test_tell_joke.py` — tests covering handler, contract guards, and fast-path routing

**Files NOT to modify:**
- `src/llm/types.py` — `ToolName` Literal is auto-generated from `TOOL_NAME_ORDER`
- `src/llm/llama_backend.py` — GBNF grammar uses `tool_name_gbnf_alternatives()` from `tool_contract.py` (auto-updates)
- `src/runtime/engine.py` — `RuntimeComponents` wiring unchanged; tell_joke needs no new collaborators
- `src/pomodoro/` — no new pomodoro cycle involvement
- `src/llm/parser_messages.py` — `fallback_assistant_text` defaults to "Anfrage verarbeitet." for unknown tools; dispatch handler always overrides it with the actual joke

**Alignment with project structure:**
- Tool follows the naming convention: `TOOL_TELL_JOKE` constant (`UPPER_SNAKE_CASE`) → `"tell_joke"` value (`snake_case`)
- Handler follows private module-level function convention: `_handle_tell_joke` (leading underscore)
- All German user-facing strings in the handler (joke text); all identifiers in English

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1] — Full acceptance criteria
- [Source: _bmad-output/project-context.md#Tool System] — Tool addition full checklist (5 steps)
- [Source: _bmad-output/project-context.md#Anti-Patterns] — ❌ Never define a tool name string outside `contracts/tool_contract.py`; ❌ Never add no-arg tool without `TOOLS_WITHOUT_ARGUMENTS`
- [Source: src/contracts/tool_contract.py] — Current `TOOL_NAME_ORDER`, `TOOLS_WITHOUT_ARGUMENTS`, `TOOL_NAMES`
- [Source: src/runtime/tools/dispatch.py] — Current `match raw_name:` structure, `import contracts.tool_contract as _tc` alias
- [Source: src/llm/fast_path.py] — `_infer_tool_call()` flow, `_tool_call()` helper
- [Source: src/llm/parser_rules.py] — Pattern for `looks_like_*` detection functions
- [Source: tests/llm/test_fast_path.py] — Import pattern for fast_path tests (llm package injection)
- [Source: _bmad-output/implementation-artifacts/3-4-web-ui-pomodoro-state-synchronisation.md#Dev Notes] — Dispatch pattern import technique, runtime injection pattern for tests

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Implemented `tell_joke` tool proving the ≤2-file tool-addition contract (AC #1): only `src/contracts/tool_contract.py` and `src/runtime/tools/dispatch.py` needed for LLM dispatch to function.
- Added `PURE_LLM_TOOL_NAMES` frozenset in `tool_contract.py` to satisfy `test_tool_contract_consistency.py` coverage assertion — without it the test would fail after `TOOL_TELL_JOKE` was added to `TOOL_NAMES`.
- `_handle_tell_joke` is a module-level function (not a method) placed before the `RuntimeToolDispatcher` class, consistent with the codebase convention. Uses `del assistant_text` to mark the parameter as intentionally unused (project rule 13).
- Fast-path detection added via `looks_like_tell_joke()` in `parser_rules.py`, inserted before action-based routing in `_infer_tool_call()` since joke requests have no action keyword.
- 13 new tests added across dispatch (3), contract guards (6), and fast-path (4). All 218 tests pass.

### File List

**Modified:**
- `src/contracts/tool_contract.py`
- `src/runtime/tools/dispatch.py`
- `src/llm/parser_rules.py`
- `src/llm/fast_path.py`
- `tests/runtime/test_tool_contract_consistency.py`

**Created:**
- `tests/runtime/test_tell_joke.py`

# Story 1.3: LLM Module Boundaries & Module Naming Corrections

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want each LLM module to have a single, clearly named responsibility with no overlapping logic,
so that parser changes carry no risk of regressions in inference logic and I can open any LLM file knowing exactly what it does.

## Acceptance Criteria

1. **Given** the LLM module boundary enforcement is complete
   **When** a developer inspects `llm/llama_backend.py`
   **Then** it contains only llama.cpp wrapper logic, GBNF grammar setup, and raw inference → raw string output
   **And** it contains no JSON parsing logic and no command routing logic

2. **Given** the LLM module boundary enforcement is complete
   **When** a developer inspects `llm/parser.py`
   **Then** it contains only raw string → `StructuredResponse` JSON normalisation and intent fallback logic
   **And** it contains no llama.cpp calls and no command routing logic

3. **Given** the LLM module boundary enforcement is complete
   **When** a developer inspects `llm/fast_path.py`
   **Then** it contains only deterministic German command routing, returning `StructuredResponse | None`
   **And** it contains no llama.cpp calls and no JSON parsing logic

4. **Given** the LLM module boundary enforcement is complete
   **When** a developer inspects `llm/service.py`
   **Then** it contains only orchestration: `llama_backend → parser` (fast-path bypass is handled at the utterance layer, above the service)
   **And** it contains no parsing logic and no grammar setup logic

5. **Given** any module in `src/` has a name that does not accurately describe its responsibility
   **When** the naming corrections are complete
   **Then** all module names accurately describe the single responsibility of their contents
   **And** no module name shadows a stdlib or third-party package name

6. **Given** the boundary enforcement and naming corrections are complete
   **When** `uv run pytest tests/runtime/test_contract_guards.py` is executed
   **Then** all guard tests pass, including any new guards added to enforce LLM module boundaries
   **And** `uv run pytest tests/` passes in full — no regressions introduced

## Tasks / Subtasks

- [x] Add `from __future__ import annotations` to LLM files that are missing it (AC: #1, #4)
  - [x] `src/llm/service.py` — insert `from __future__ import annotations` as the first non-docstring line (before `import logging`)
  - [x] `src/llm/llama_backend.py` — insert `from __future__ import annotations` as the first non-docstring line (before `from dataclasses import dataclass`)
  - [x] `src/llm/parser_extractors.py` — insert `from __future__ import annotations` as the first non-docstring line (before `from datetime import datetime...`)

- [x] Refactor `llm/fast_path.py` to remove `ResponseParser` dependency (AC: #3)
  - [x] Extract a standalone `infer_tool_call_from_prompt(prompt: str) -> ToolCall | None` function into `llm/parser_rules.py` (or a new `llm/intent.py`) that is stateless — no `_last_focus_topic` / `_last_time_range` session state (these belong only in `ResponseParser`)
  - [x] The standalone function must call into `parser_rules` (detect_action, has_pomodoro_context, etc.) and `parser_extractors` (extract_duration_from_prompt, sanitize_text, etc.) directly
  - [x] Update `llm/fast_path.py` to import this standalone function instead of `ResponseParser`
  - [x] Remove the `from .parser import ResponseParser` import from `fast_path.py`
  - [x] Update `tests/llm/test_fast_path.py`: replace `test_fast_path_uses_parser_public_api` (which patches `llm.fast_path.ResponseParser`) with an equivalent test that patches the new import target
  - [x] Verify all existing fast_path behavioural tests still pass

- [x] Rename `stt/stt.py` → `stt/transcription.py` (AC: #5)
  - [x] Rename the file from `src/stt/stt.py` to `src/stt/transcription.py`
  - [x] Update `src/runtime/workers/stt.py` — 3 import sites:
    - `from stt.stt import TranscriptionResult` → `from stt.transcription import TranscriptionResult`
    - `from stt.stt import FasterWhisperSTT` → `from stt.transcription import FasterWhisperSTT`
    - `from stt.stt import STTError` → `from stt.transcription import STTError`
  - [x] Update `src/contracts/pipeline.py`: `from stt.stt import TranscriptionResult` → `from stt.transcription import TranscriptionResult`
  - [x] Update `src/runtime/utterance.py`: `from stt.stt import STTError` → `from stt.transcription import STTError`
  - [x] Update `tests/stt/test_stt_download_root.py`: `from stt.stt import ...` → `from stt.transcription import ...`; patch target `stt.stt.WhisperModel` → `stt.transcription.WhisperModel`
  - [x] Update `tests/runtime/test_utterance_state_flow.py`: `types.ModuleType("stt.stt")` stub → `types.ModuleType("stt.transcription")`; update sys.modules key from `"stt.stt"` to `"stt.transcription"`

- [x] Add LLM module boundary guard tests (AC: #6)
  - [x] Add a new `LlmModuleBoundaryGuards` class in `tests/runtime/test_contract_guards.py`
  - [x] Guard 1: `llm/fast_path.py` must not contain `from .parser import` or `from llm.parser import` (enforces boundary between fast_path and parser)
  - [x] Guard 2: `llm/llama_backend.py` must not contain `import json` or `from json` (no JSON parsing in the inference wrapper)
  - [x] Guard 3: `llm/parser.py` must not contain `from llama_cpp` or `import llama_cpp` (no llama.cpp in the parser)
  - [x] Guard 4: `llm/fast_path.py` must not contain `from __future__` violation — i.e., all LLM files in the boundary must have `from __future__ import annotations` as first code line

- [x] Run full test suite (AC: #6)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — all guard tests pass including new LLM boundary guards
  - [x] `uv run pytest tests/` — all tests pass, zero regressions

## Dev Notes

### Current State — Exact Violations

#### Violation 1: `llm/fast_path.py` imports `ResponseParser`

```python
# CURRENT — violates the boundary (fast_path must not depend on parser)
from .parser import ResponseParser

def maybe_fast_path_response(user_prompt: str) -> StructuredResponse | None:
    parser = ResponseParser()
    tool_call = parser.infer_tool_call_from_prompt(prompt)
    ...
    return {
        "assistant_text": parser.fallback_assistant_text(tool_call),
        "tool_call": tool_call,
    }
```

`fast_path.py` must NOT import from `parser.py`. The `ResponseParser` class is the LLM output JSON parser. Even though `infer_tool_call_from_prompt` doesn't parse JSON itself, the structural coupling violates the boundary. The underlying logic in `infer_tool_call_from_prompt` calls `parser_rules` functions (`detect_action`, `has_pomodoro_context`, etc.) and `parser_extractors` functions (`normalize_duration`, etc.) which are already in separate modules. These should be imported directly.

#### Violation 2: Missing `from __future__ import annotations`

```python
# llm/service.py — CURRENT (wrong)
"""High-level LLM service..."""

import logging          # ← __future__ import is MISSING

# llm/llama_backend.py — CURRENT (wrong)
"""llama.cpp backend wrapper..."""

from dataclasses import dataclass  # ← __future__ import is MISSING
```

Per project rules, **every module must begin with `from __future__ import annotations`** — no exceptions. The docstring can precede it, but `from __future__ import annotations` must be the first **import** statement.

#### Violation 3: `stt/stt.py` — Self-Referential Module Name

```python
# CURRENT — confusing imports project-wide
from stt.stt import TranscriptionResult   # awkward: module named after its package
from stt.stt import FasterWhisperSTT
from stt.stt import STTError
```

`stt.stt` means "the `stt` module within the `stt` package". This is a naming anti-pattern. The file contains `FasterWhisperSTT` (faster-whisper implementation) + `StreamingFasterWhisperSTT` + `TranscriptionResult` + `STTError`. A correct name for this scope is `transcription.py`.

### Target Implementation

#### Fix 1: Refactor `fast_path.py`

```python
# TARGET — fast_path.py after fix
from __future__ import annotations

from .parser_extractors import (
    extract_duration_from_prompt,
    extract_focus_topic,
    normalize_duration,
    sanitize_text,
    sanitize_time_range,
    extract_time_range,
    extract_calendar_title,
    normalize_calendar_datetime_input,
)
from .parser_messages import fallback_assistant_text
from .parser_rules import (
    detect_action,
    has_pomodoro_context,
    has_timer_context,
    looks_like_add_calendar,
    looks_like_show_events,
)
from .types import StructuredResponse, ToolCall, ToolName
from contracts.tool_contract import (
    INTENT_TO_POMODORO_TOOL,
    INTENT_TO_TIMER_TOOL,
    TOOL_ADD_CALENDAR_EVENT,
    TOOL_SHOW_UPCOMING_EVENTS,
    TOOL_START_POMODORO,
    TOOL_START_TIMER,
    TOOLS_WITHOUT_ARGUMENTS,
    DEFAULT_CALENDAR_TIME_RANGE,
)
from shared.defaults import (
    DEFAULT_FOCUS_TOPIC_DE,
    DEFAULT_TIMER_MINUTES,
    DEFAULT_CALENDAR_TIME_RANGE,
)
from typing import cast


def maybe_fast_path_response(user_prompt: str) -> StructuredResponse | None:
    """Return a deterministic response for explicit tool intents.

    Bypasses llama.cpp entirely by applying stateless intent detection rules.
    Returns None if no deterministic tool intent is recognised.
    """
    prompt = user_prompt.strip()
    if not prompt:
        return None

    tool_call = _infer_tool_call(prompt)
    if tool_call is None:
        return None

    return {
        "assistant_text": fallback_assistant_text(tool_call),
        "tool_call": tool_call,
    }


def _infer_tool_call(prompt: str) -> ToolCall | None:
    """Stateless deterministic intent → ToolCall mapping."""
    lowered = prompt.lower()

    if looks_like_add_calendar(lowered):
        ...  # similar logic to ResponseParser._infer_tool_call_from_prompt

    if looks_like_show_events(lowered):
        ...

    action = detect_action(prompt)
    if action is None:
        return None
    # ... rest of intent routing
```

**Key constraint**: The standalone `_infer_tool_call` (or extracted function) must be **stateless** — no `_last_focus_topic` / `_last_time_range`. Those session variables belong only in `ResponseParser`. For calendar arguments that need defaults, use the module-level defaults directly.

**Important**: `ResponseParser._infer_tool_call_from_prompt()` has session state that provides "memory" of the last used focus topic or time range. The fast-path implementation should NOT have this state — it should always fall back to `DEFAULT_FOCUS_TOPIC_DE` and `DEFAULT_CALENDAR_TIME_RANGE`. This is correct for fast-path because: (a) fast-path is for deterministic commands which are clear enough to not need session context, (b) session context is for when the LLM needs to remember things across turns.

**Concrete `_infer_tool_call` implementation guide** — mirror `ResponseParser._infer_tool_call_from_prompt` but stateless:

```python
def _infer_tool_call(prompt: str) -> ToolCall | None:
    lowered = prompt.lower()

    # Calendar: add event
    if looks_like_add_calendar(lowered):
        from datetime import datetime
        now_fn = lambda: datetime.now().astimezone()
        title = sanitize_text(extract_calendar_title(prompt), max_len=120)
        start_time = normalize_calendar_datetime_input(None, now_fn=now_fn) or \
                     extract_datetime_literal(prompt, now_fn=now_fn)
        # If we cannot determine both title and start_time, don't fast-path this
        title_extracted = sanitize_text(extract_calendar_title(prompt), max_len=120)
        start_extracted = extract_datetime_literal(prompt, now_fn=now_fn)
        if not title_extracted or not start_extracted:
            return None
        payload: dict[str, Any] = {"title": title_extracted, "start_time": start_extracted}
        return _tool_call(TOOL_ADD_CALENDAR_EVENT, payload)

    # Calendar: show events
    if looks_like_show_events(lowered):
        time_range = sanitize_time_range(
            extract_time_range(prompt) or DEFAULT_CALENDAR_TIME_RANGE
        )
        return _tool_call(TOOL_SHOW_UPCOMING_EVENTS, {"time_range": time_range})

    action = detect_action(prompt)
    if action is None:
        return None

    has_pomodoro = has_pomodoro_context(lowered)
    has_timer = has_timer_context(lowered)
    duration = extract_duration_from_prompt(prompt)

    if has_pomodoro:
        name = INTENT_TO_POMODORO_TOOL.get(action)
        if name is None:
            return None
        if name == TOOL_START_POMODORO:
            topic = sanitize_text(extract_focus_topic(prompt) or DEFAULT_FOCUS_TOPIC_DE, max_len=60)
            return _tool_call(name, {"focus_topic": topic})
        if name in TOOLS_WITHOUT_ARGUMENTS:
            return _tool_call(name, {})
        return None

    if has_timer or duration is not None:
        name = INTENT_TO_TIMER_TOOL.get(action)
        if name is None:
            return None
        if name == TOOL_START_TIMER:
            dur = normalize_duration(duration) or str(DEFAULT_TIMER_MINUTES)
            return _tool_call(name, {"duration": dur})
        if name in TOOLS_WITHOUT_ARGUMENTS:
            return _tool_call(name, {})
        return None

    return None


def _tool_call(name: str, arguments: dict[str, Any]) -> ToolCall:
    from typing import cast
    from .types import ToolName
    return {"name": cast(ToolName, name), "arguments": arguments}
```

**Note**: `INTENT_TO_POMODORO_TOOL` and `INTENT_TO_TIMER_TOOL` may not exist as separate dicts in `contracts/tool_contract.py`. Check actual names — they may be `INTENT_TO_POMODORO_TOOL` and `INTENT_TO_TIMER_TOOL` (imported by `parser.py` from `contracts.tool_contract`). Use the same import as in `parser.py`.

**`stt/__init__.py` check**: The `stt/__init__.py` only exports `create_stt_resources` from `factory.py`. It does NOT import from `stt.stt`. **No changes needed to `stt/__init__.py`**.

#### Fix 2: `from __future__ import annotations` placement

Python convention: docstrings can appear before future imports, but per this project's pattern (and PEP 563), the `from __future__ import annotations` must be the first **code** statement.

Looking at existing compliant files like `runtime/utterance.py`:
```python
"""Utterance pipeline..."""  # module docstring OK before future import

from __future__ import annotations  # ← first code line

import logging
...
```

Apply this same pattern to `service.py` and `llama_backend.py`.

#### Fix 3: Rename stt/stt.py → stt/transcription.py

No logic changes. Pure rename + import site updates.

```
src/stt/stt.py  →  src/stt/transcription.py
```

Import sites to update (5 files):

| File | Old import | New import |
|------|-----------|------------|
| `src/runtime/workers/stt.py` line 17 | `from stt.stt import TranscriptionResult` | `from stt.transcription import TranscriptionResult` |
| `src/runtime/workers/stt.py` line 27 | `from stt.stt import FasterWhisperSTT` | `from stt.transcription import FasterWhisperSTT` |
| `src/runtime/workers/stt.py` line 75 | `from stt.stt import STTError` | `from stt.transcription import STTError` |
| `src/contracts/pipeline.py` line 10 | `from stt.stt import TranscriptionResult` | `from stt.transcription import TranscriptionResult` |
| `src/runtime/utterance.py` line 11 | `from stt.stt import STTError` | `from stt.transcription import STTError` |

Test files to update (2 files):

| File | Change needed |
|------|--------------|
| `tests/stt/test_stt_download_root.py` | `from stt.stt import ...` → `from stt.transcription import ...`; patch target `stt.stt.WhisperModel` → `stt.transcription.WhisperModel` |
| `tests/runtime/test_utterance_state_flow.py` | `types.ModuleType("stt.stt")` → `types.ModuleType("stt.transcription")`; `sys.modules["stt.stt"]` → `sys.modules["stt.transcription"]` |

#### Fix 4: New Guard Tests

```python
# Add to tests/runtime/test_contract_guards.py

_LLM_FAST_PATH = _ROOT / "src" / "llm" / "fast_path.py"
_LLM_LLAMA_BACKEND = _ROOT / "src" / "llm" / "llama_backend.py"
_LLM_PARSER = _ROOT / "src" / "llm" / "parser.py"
_LLM_SERVICE = _ROOT / "src" / "llm" / "service.py"

class LlmModuleBoundaryGuards(unittest.TestCase):
    def test_fast_path_does_not_import_from_parser(self) -> None:
        source = _LLM_FAST_PATH.read_text(encoding="utf-8")
        self.assertNotIn(
            "from .parser import",
            source,
            msg="fast_path.py must not import from parser.py — violates module boundary",
        )
        self.assertNotIn(
            "from llm.parser import",
            source,
            msg="fast_path.py must not import from llm.parser — violates module boundary",
        )

    def test_llama_backend_does_not_contain_json_parsing(self) -> None:
        source = _LLM_LLAMA_BACKEND.read_text(encoding="utf-8")
        self.assertNotIn(
            "import json",
            source,
            msg="llama_backend.py must not contain JSON parsing — that belongs in parser.py",
        )
        self.assertNotRegex(
            source,
            r"json\.loads|json\.dumps",
            msg="llama_backend.py must not use json.loads/dumps",
        )

    def test_parser_does_not_import_from_llama_cpp(self) -> None:
        source = _LLM_PARSER.read_text(encoding="utf-8")
        self.assertNotIn(
            "llama_cpp",
            source,
            msg="parser.py must not import from llama_cpp",
        )

    def test_llm_boundary_files_have_future_annotations(self) -> None:
        _LLM_EXTRACTORS = _ROOT / "src" / "llm" / "parser_extractors.py"
        for path in (_LLM_FAST_PATH, _LLM_LLAMA_BACKEND, _LLM_PARSER, _LLM_SERVICE, _LLM_EXTRACTORS):
            source = path.read_text(encoding="utf-8")
            self.assertIn(
                "from __future__ import annotations",
                source,
                msg=f"{path.name} is missing 'from __future__ import annotations'",
            )
```

### `runtime/tools/messages.py` — No Rename Required

The architecture ADR explicitly lists `runtime/tools/messages.py ← German status/fallback messages` in the target structure. The module name accurately describes its content. The epics document mentions it as a "misleading module name example" but the authoritative architecture doc keeps the name. **No action needed here for this story.**

### Test Impact Analysis

- **`tests/llm/test_fast_path.py`**: `test_fast_path_uses_parser_public_api` patches `llm.fast_path.ResponseParser`. After the refactor, this test must be rewritten to patch the correct import target (the new standalone function or the `parser_rules`/`parser_messages` imports). The two behavioural tests (`test_fast_path_infers_timer_tool_call`, `test_fast_path_returns_none_for_non_action_prompt`) should continue to pass unchanged since behaviour is preserved.

- **`tests/stt/test_stt_download_root.py`**: Pure string updates (`stt.stt` → `stt.transcription`). No logic changes.

- **`tests/runtime/test_utterance_state_flow.py`**: Stub module name update only.

- **`tests/runtime/test_contract_guards.py`**: New `LlmModuleBoundaryGuards` class added — no existing tests modified.

**Total test count after story**: Should remain at 145 or increase slightly if a replacement for the patched fast_path test is kept.

### Architecture Compliance Checklist

- `from __future__ import annotations` must be first code line in ALL modified files
- `stt/transcription.py` must NOT be renamed to shadow a stdlib or third-party package (no `from faster_whisper import` visible at module level — keep the deferred import pattern that's already in `stt.py`)
- `llm/fast_path.py` refactored version must NOT introduce mutable module-level state
- New guard tests must follow `unittest.TestCase` base class pattern
- Run `uv run pytest tests/runtime/test_contract_guards.py` after every structural change before the full suite
- Do NOT add `@dataclass(frozen=True, slots=True)` to anything in this story — that is Story 1.4's scope
- Do NOT modify dispatch logic or tool contract — not in scope
- This is Step 4 of 8 in Phase 1. Follows Story 1.2 (config boundary — done). Precedes 1.4 (frozen value objects).

### Project Structure Notes

- `src/` is on `sys.path` — all imports use module name directly without `src.` prefix
- Rename: `src/stt/stt.py` → `src/stt/transcription.py` — no changes to `stt/__init__.py` needed unless it re-exports from `stt`
- Check `src/stt/__init__.py` for any existing re-exports of `stt.stt` names before renaming
- The `FasterWhisperSTT` and `StreamingFasterWhisperSTT` classes use `from faster_whisper import WhisperModel` at the top of the file — this is a native dependency that loads on import. The existing test stub pattern (`sys.modules` patching) handles this correctly and should continue to work after the rename.

### References

- Epics file: `_bmad-output/planning-artifacts/epics.md` — Story 1.3 acceptance criteria
- Architecture ADR: `_bmad-output/planning-artifacts/architecture.md` — "LLM Module Boundary Rules" section (4-file table), "Naming Patterns" section
- Project context: `_bmad-output/project-context.md` — Rule 1 (import style), anti-patterns section
- `src/llm/fast_path.py` — primary change target (remove ResponseParser import)
- `src/llm/service.py` — add `from __future__ import annotations`
- `src/llm/llama_backend.py` — add `from __future__ import annotations`
- `src/stt/stt.py` — rename to `src/stt/transcription.py`
- `tests/runtime/test_contract_guards.py` — add `LlmModuleBoundaryGuards` class
- Implementation sequence note: Step 4 of 8. Previous story 1-2 is done. Next is 1-4 (frozen value objects + pattern matching dispatch).

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No issues encountered. All tasks completed in a single session without debug halts.

### Completion Notes List

- Added `from __future__ import annotations` to `service.py`, `llama_backend.py`, and `parser_extractors.py` as first code line after module docstring.
- Refactored `fast_path.py`: replaced `ResponseParser` import with direct imports from `parser_rules`, `parser_extractors`, `parser_messages`, `contracts.tool_contract`, and `shared.defaults`. Implemented stateless `_infer_tool_call()` private function that mirrors `ResponseParser._infer_tool_call_from_prompt` without session state (`_last_focus_topic`/`_last_time_range`). All behavioural tests continue to pass.
- Renamed `src/stt/stt.py` → `src/stt/transcription.py` via `git mv`. Updated 5 source import sites and 2 test import sites (including patch targets and sys.modules stubs). `stt/__init__.py` required no changes as confirmed by inspection.
- Added `LlmModuleBoundaryGuards` class with 4 guard tests to `tests/runtime/test_contract_guards.py`. Guards enforce: fast_path doesn't import parser, llama_backend has no JSON parsing, parser has no llama_cpp imports, all boundary files have `from __future__ import annotations`.
- Full suite: 149 tests pass, 0 regressions. Test count increased by 4 (new guard tests).
- Code review 2: fixed 4 MEDIUM issues — added `from __future__ import annotations` to all 4 modified files missing it (`tests/llm/test_fast_path.py`, `tests/stt/test_stt_download_root.py`, `tests/runtime/test_utterance_state_flow.py`; `src/stt/transcription.py` was already fixed by story 1-4 working-tree pre-work). Removed PEP 8 lambda-as-named-variable in `fast_path.py:_infer_tool_call` (replaced `now_fn = lambda: ...` + `extract_datetime_literal(prompt, now_fn=now_fn)` with direct `extract_datetime_literal(prompt)`, relying on the default `now_fn=None` behaviour); removed now-unused `from datetime import datetime` import. 153 tests pass (includes 4 new DispatchPatternGuards from story 1-4 pre-work already in working tree).

### File List

- `src/llm/fast_path.py` — refactored: removed ResponseParser dependency, stateless _infer_tool_call
- `src/llm/service.py` — added `from __future__ import annotations`; removed dead accounting code (getattr-based pre-computation immediately overwritten by usage object); switched to direct property access; removed redundant string forward reference on classmethod return type
- `src/llm/llama_backend.py` — added `from __future__ import annotations`
- `src/llm/parser_extractors.py` — added `from __future__ import annotations`
- `src/stt/transcription.py` — renamed from stt/stt.py; moved `from faster_whisper import WhisperModel` to deferred import inside FasterWhisperSTT.__init__ (architecture compliance); converted 5 f-string logging calls to %s-style deferred formatting
- `src/runtime/workers/stt.py` — updated 3 import sites stt.stt → stt.transcription
- `src/contracts/pipeline.py` — updated 1 import site stt.stt → stt.transcription
- `src/runtime/utterance.py` — updated 1 import site stt.stt → stt.transcription
- `tests/llm/test_fast_path.py` — replaced test_fast_path_uses_parser_public_api with test_fast_path_uses_parser_rules_not_response_parser
- `tests/stt/test_stt_download_root.py` — updated import and patch target: stt.stt → stt.transcription; updated patch target from stt.transcription.WhisperModel → faster_whisper.WhisperModel (deferred import fix)
- `tests/runtime/test_utterance_state_flow.py` — updated stub module name and sys.modules key
- `tests/runtime/test_contract_guards.py` — added LlmModuleBoundaryGuards class (4 new guard tests)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status updated to review
- `_bmad-output/implementation-artifacts/1-3-llm-module-boundaries-module-naming-corrections.md` — story updated

## Change Log

- 2026-02-28: Implemented LLM module boundaries and module naming corrections — refactored fast_path.py to remove ResponseParser dependency, added `from __future__ import annotations` to 3 LLM files, renamed stt/stt.py → stt/transcription.py with all import site updates, added 4 new LLM boundary guard tests. 149 tests pass, 0 regressions.
- 2026-02-28: Code review — fixed 5 issues (1 HIGH, 4 MEDIUM): corrected AC #4 wording (service.py orchestrates llama_backend→parser, not fast_path); fixed stale `package.stt` attribute in test stub (→ `package.transcription`); fixed pipeline.py docstring ordering (future import must follow docstring); strengthened Guard 4 to check position of future import, not just presence; added `from json import` pattern to Guard 2. 149 tests pass, 0 regressions.
- 2026-02-28: Code review 2 — fixed 4 MEDIUM + 1 LOW: added `from __future__ import annotations` to `tests/llm/test_fast_path.py`, `tests/stt/test_stt_download_root.py`, `tests/runtime/test_utterance_state_flow.py` (architecture compliance checklist: all modified files); removed PEP 8 lambda-as-named-variable from `fast_path.py` + removed now-unused `datetime` import. Note: `src/stt/transcription.py` future import already present via story 1-4 working-tree pre-work. 153 tests pass, 0 regressions.
- 2026-02-28: Code review 3 — fixed 1 HIGH + 3 MEDIUM + 1 LOW: [H1] moved `from faster_whisper import WhisperModel` from module level to deferred import inside `FasterWhisperSTT.__init__` (architecture compliance checklist violation); updated `tests/stt/test_stt_download_root.py` patch target from `stt.transcription.WhisperModel` → `faster_whisper.WhisperModel`; [M1+M3] removed dead accounting code in `service.py run()` — getattr-based pre-computation was immediately overwritten by usage object, replaced with direct `self._backend.last_usage` property access and explicit if/else; [M2] converted 5 f-string logging calls in `transcription.py` to `%s`-style deferred formatting; [L1] removed redundant string forward reference `"PomodoroAssistantLLM"` on `from_model_path` return type. 154 tests pass, 0 regressions.

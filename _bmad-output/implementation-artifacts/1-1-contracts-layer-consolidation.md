# Story 1.1: Contracts Layer Consolidation

Status: done

## Story

As a developer,
I want all Protocol definitions and IPC envelope types consolidated into a single `src/contracts/` namespace,
so that I can locate any interface without tracing import chains and "where does a new interface go?" has one unambiguous answer.

## Acceptance Criteria

1. **Given** `src/runtime/contracts.py` and `src/oracle/contracts.py` contain Protocol and container definitions
   **When** the consolidation is complete
   **Then** `STTClient`, `LLMClient`, `TTSClient` Protocol definitions exist in `src/contracts/pipeline.py`
   **And** `src/runtime/contracts.py` is dissolved — the file no longer exists
   **And** `src/oracle/contracts.py` contents are absorbed into `src/contracts/oracle.py`
   **And** all import sites throughout the codebase are updated to import from `src/contracts/`

2. **Given** `_RequestEnvelope` and `_ResponseEnvelope` are defined inside `src/runtime/workers/core.py`
   **When** the consolidation is complete
   **Then** both types exist in `src/contracts/ipc.py` as `@dataclass(frozen=True, slots=True)` typed dataclasses
   **And** `_ProcessWorker` / `_worker_process_loop` in `core.py` import them from `src/contracts/ipc.py` — no local definition remains

3. **Given** the consolidation is complete
   **When** `uv run pytest tests/runtime/test_contract_guards.py` is executed
   **Then** all guard tests pass with no violations (including any new guards added for contracts consolidation)
   **And** `uv run pytest tests/` passes in full — no regressions introduced

## Tasks / Subtasks

- [x] Create `src/contracts/pipeline.py` (AC: #1)
  - [x] Move `STTClient`, `LLMClient`, `TTSClient` from `src/runtime/contracts.py`; preserve all TYPE_CHECKING imports
  - [x] Add `from __future__ import annotations` as first line
- [x] Create `src/contracts/oracle.py` (AC: #1)
  - [x] Move `OracleProviders` dataclass from `src/oracle/contracts.py`
  - [x] Add `from __future__ import annotations` as first line
- [x] Create `src/contracts/ipc.py` (AC: #2)
  - [x] Promote `_RequestEnvelope` and `_ResponseEnvelope` dataclasses (copy definitions, keep `frozen=True, slots=True`)
  - [x] Add `from __future__ import annotations` as first line
  - [x] Do NOT move `_StopSignal`, `_STOP_SIGNAL` — they are internal implementation details of `core.py`
- [x] Update `src/contracts/__init__.py` (AC: #1)
  - [x] Keep `StartupError`; add re-exports for the full public surface: `STTClient`, `LLMClient`, `TTSClient`, `OracleProviders`, `_RequestEnvelope`, `_ResponseEnvelope`
- [x] Update all import sites (AC: #1, #2)
  - [x] `src/runtime/ticks.py`: `from .contracts import TTSClient` → `from contracts.pipeline import TTSClient`
  - [x] `src/runtime/utterance.py`: `from .contracts import LLMClient, STTClient, TTSClient` → `from contracts.pipeline import LLMClient, STTClient, TTSClient`
  - [x] `src/runtime/engine.py`: `from .contracts import LLMClient, STTClient, TTSClient` → `from contracts.pipeline import LLMClient, STTClient, TTSClient`
  - [x] `src/oracle/service.py`: `from .contracts import OracleProviders` → `from contracts.oracle import OracleProviders`
  - [x] `src/oracle/providers.py`: `from .contracts import OracleProviders` → `from contracts.oracle import OracleProviders`
  - [x] `src/runtime/workers/core.py`: add `from contracts.ipc import _RequestEnvelope, _ResponseEnvelope`; remove local dataclass definitions for both types
- [x] Delete dissolved files (AC: #1)
  - [x] Delete `src/runtime/contracts.py`
  - [x] Delete `src/oracle/contracts.py`
- [x] Add guard tests to `tests/runtime/test_contract_guards.py` (AC: #3)
  - [x] Assert `src/runtime/contracts.py` does not exist
  - [x] Assert `src/oracle/contracts.py` does not exist
  - [x] Assert no source file in `src/` imports from `runtime.contracts` or `oracle.contracts`
- [x] Run full test suite (AC: #3)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — all pass (4/4)
  - [x] `uv run pytest tests/` — all pass (138/138), zero regressions

## Dev Notes

### What Actually Exists Right Now (Current State)

**`src/runtime/contracts.py`** (3 Protocols — dissolve this file):
```python
class STTClient(Protocol):
    def transcribe(self, utterance: "Utterance") -> "TranscriptionResult": ...

class LLMClient(Protocol):
    def run(self, user_prompt: str, *, env: "EnvironmentContext" | None = None,
            extra_context: str | None = None, max_tokens: int | None = None) -> "StructuredResponse": ...

class TTSClient(Protocol):
    def speak(self, text: str) -> None: ...
```

**`src/oracle/contracts.py`** (1 dataclass — dissolve this file):
```python
@dataclass(frozen=True, slots=True)
class OracleProviders:
    ens160: object | None = None
    temt6000: object | None = None
    calendar: object | None = None
```

**`src/runtime/workers/core.py`** (lines 44–57 — promote to `contracts/ipc.py`):
```python
@dataclass(frozen=True, slots=True)
class _RequestEnvelope:
    call_id: int
    payload: object

@dataclass(frozen=True, slots=True)
class _ResponseEnvelope:
    kind: str
    call_id: int | None = None
    payload: object | None = None
    error_type: str | None = None
    error_message: str | None = None
```

**`src/contracts/__init__.py`** (current — only has `StartupError`):
```python
class StartupError(Exception):
    """Raised when runtime startup cannot continue."""
```

### Exact Import Sites That Require Updates

| File | Current import | New import |
|------|---------------|------------|
| `src/runtime/ticks.py:18` | `from .contracts import TTSClient` | `from contracts.pipeline import TTSClient` |
| `src/runtime/utterance.py:25` | `from .contracts import LLMClient, STTClient, TTSClient` | `from contracts.pipeline import LLMClient, STTClient, TTSClient` |
| `src/runtime/engine.py:37` | `from .contracts import LLMClient, STTClient, TTSClient` | `from contracts.pipeline import LLMClient, STTClient, TTSClient` |
| `src/oracle/service.py:11` | `from .contracts import OracleProviders` | `from contracts.oracle import OracleProviders` |
| `src/oracle/providers.py:9` | `from .contracts import OracleProviders` | `from contracts.oracle import OracleProviders` |
| `src/runtime/workers/core.py` | local definitions (lines 44–57) | `from contracts.ipc import _RequestEnvelope, _ResponseEnvelope` |

### What NOT to Move (Stay in `core.py`)

- `_StopSignal` and `_STOP_SIGNAL` — internal IPC shutdown signal, not a public contract
- `_WorkerRuntime` Protocol — internal factory protocol, not part of the public contracts surface
- `WorkerRuntimeFactory` type alias — internal, stays in `core.py`
- `WorkerError`, `WorkerInitError`, `WorkerClosedError`, `WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError` — these are runtime error types, NOT moved in this story (architecture does not specify relocating them in Story 1.1)

### New Files to Create

**`src/contracts/pipeline.py`:**
```python
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from llm.types import EnvironmentContext, StructuredResponse
    from stt.events import Utterance
    from stt.stt import TranscriptionResult


class STTClient(Protocol):
    def transcribe(self, utterance: "Utterance") -> "TranscriptionResult": ...


class LLMClient(Protocol):
    def run(
        self,
        user_prompt: str,
        *,
        env: "EnvironmentContext" | None = None,
        extra_context: str | None = None,
        max_tokens: int | None = None,
    ) -> "StructuredResponse": ...


class TTSClient(Protocol):
    def speak(self, text: str) -> None: ...
```

**`src/contracts/oracle.py`:**
```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OracleProviders:
    """Container bundling optional provider instances built at startup."""
    ens160: object | None = None
    temt6000: object | None = None
    calendar: object | None = None
```

**`src/contracts/ipc.py`:**
```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _RequestEnvelope:
    call_id: int
    payload: object


@dataclass(frozen=True, slots=True)
class _ResponseEnvelope:
    kind: str
    call_id: int | None = None
    payload: object | None = None
    error_type: str | None = None
    error_message: str | None = None
```

### Target `src/contracts/__init__.py` After Consolidation

```python
from __future__ import annotations

"""Shared cross-module contracts and protocol constants."""

from contracts.ipc import _RequestEnvelope, _ResponseEnvelope
from contracts.oracle import OracleProviders
from contracts.pipeline import LLMClient, STTClient, TTSClient


class StartupError(Exception):
    """Raised when runtime startup cannot continue."""


__all__ = [
    "StartupError",
    "STTClient",
    "LLMClient",
    "TTSClient",
    "OracleProviders",
    "_RequestEnvelope",
    "_ResponseEnvelope",
]
```

### Target `src/contracts/` Directory Structure After Story

```
src/contracts/
├── __init__.py        ← StartupError + re-exports full public surface
├── tool_contract.py   ← unchanged (TOOL_* constants, TOOL_NAME_ORDER, etc.)
├── ui_protocol.py     ← unchanged (EVENT_*, STATE_* WebSocket constants)
├── pipeline.py        ← NEW: STTClient, LLMClient, TTSClient Protocols
├── ipc.py             ← NEW: _RequestEnvelope, _ResponseEnvelope dataclasses
└── oracle.py          ← NEW: OracleProviders dataclass
```

### Guard Tests Added to `tests/runtime/test_contract_guards.py`

Added `ContractsConsolidationGuards` class with two new tests:
- `test_dissolved_contracts_modules_no_longer_exist` — asserts both `src/runtime/contracts.py` and `src/oracle/contracts.py` are deleted
- `test_no_source_file_imports_from_dissolved_contracts_modules` — scans all `src/` Python files for references to `runtime.contracts` or `oracle.contracts`

### Project Structure Notes

- `src/` is on `sys.path` — use **absolute imports**: `from contracts.pipeline import STTClient`, NOT `from .pipeline import STTClient` when importing from within contracts. Other modules outside `contracts/` use `from contracts.pipeline import ...` (no `src.` prefix needed).
- Tests that import oracle or runtime modules may use `sys.modules` pre-patching — see existing test patterns in `tests/oracle/test_oracle_providers.py` and `tests/runtime/test_process_workers_recovery.py`.
- The test file `tests/oracle/test_oracle_providers.py` imports `oracle.providers.build_oracle_providers` — since that function will now import `OracleProviders` from `contracts.oracle` instead of `oracle.contracts`, it will continue to work without changes to the test file itself.
- `src/runtime/README.md` has a stale reference to `contracts.py` — update if it exists, but don't block on it.

### Architecture Compliance Requirements

- `from __future__ import annotations` **must be the first line** of every new Python module (no exceptions)
- All new `@dataclass` types in `ipc.py` must be `@dataclass(frozen=True, slots=True)` — no plain `@dataclass`
- Naming convention: module files use `snake_case.py`; never shadow stdlib (`contracts/` is fine, just don't create `contracts/json.py` etc.)
- Import style in all edited files: use `X | Y` for unions — never `Optional[X]` or `Union[X, Y]`
- Never call `multiprocessing.Process(...)` directly — always use `_ProcessWorker`; this is unchanged by this story
- `src/contracts/oracle.py` must NOT contain Protocols (oracle service protocols, if needed, go to `contracts/pipeline.py`); `OracleProviders` is a value object container, not a Protocol

### Testing Standards

- Test runner: `uv run pytest tests/`
- Test base: `unittest.TestCase`
- No new tests are required for this story beyond the guard test additions — the existing test suite exercises all affected code paths; the story's validation is passing the full suite clean
- `uv run pytest tests/runtime/test_contract_guards.py -v` should be run first as the architectural sanity check

### References

- Epics file: `_bmad-output/planning-artifacts/epics.md` — Story 1.1 acceptance criteria
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "Contracts & Interface Architecture" section, "Where New Things Go" decision table, "Naming Patterns"
- Current `src/runtime/contracts.py` — dissolve this file
- Current `src/oracle/contracts.py` — dissolve this file
- Current `src/runtime/workers/core.py` (lines 44–57) — promote `_RequestEnvelope`/`_ResponseEnvelope`
- Current `src/contracts/__init__.py` — expand to full re-export surface
- Architecture sequence note: `src/contracts/` consolidation is Step 1 of 8 in the Phase 1 implementation sequence — **all other Phase 1 stories depend on this being stable first**

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was clean with one self-corrected mistake (removed `dataclass` import from `core.py` and then restored it).

### Completion Notes List

- Created `src/contracts/pipeline.py` with `STTClient`, `LLMClient`, `TTSClient` Protocol definitions
- Created `src/contracts/oracle.py` with `OracleProviders` dataclass (absorbed from `oracle/contracts.py`)
- Created `src/contracts/ipc.py` with `_RequestEnvelope` and `_ResponseEnvelope` dataclasses (promoted from `core.py`)
- Updated `src/contracts/__init__.py` to re-export full public contracts surface
- Updated 5 import sites: `runtime/ticks.py`, `runtime/utterance.py`, `runtime/engine.py`, `oracle/service.py`, `oracle/providers.py`
- Updated `runtime/workers/core.py`: imports from `contracts.ipc`, removed local envelope definitions
- Dissolved `src/runtime/contracts.py` and `src/oracle/contracts.py` (deleted)
- Added `ContractsConsolidationGuards` class to `tests/runtime/test_contract_guards.py`
- Fixed pre-existing test failures: added `[tool.pytest.ini_options] pythonpath = ["src"]` to `pyproject.toml` (2 tests were failing due to missing `src/` on sys.path) and updated `tests/oracle/test_oracle_context_service.py` import from dissolved module
- Added `pytest` as a dev dependency via `uv add --dev pytest`
- Final result: 138 tests passed, 0 failed

### Code Review Record (2026-02-28)

**Reviewer:** claude-sonnet-4-6 (adversarial review)
**Result:** 6 issues fixed, story status → done

**Fixes applied:**
- `src/contracts/pipeline.py`: removed redundant string quotes from Protocol method annotations — with `from __future__ import annotations` active they produced double-nested strings (`'"Utterance"'`) that break `typing.get_type_hints()`
- `src/oracle/service.py`: reordered imports — absolute `from contracts.oracle import OracleProviders` now precedes relative imports per PEP 8
- `src/oracle/providers.py`: same import grouping fix
- `src/runtime/ticks.py`: grouped both `contracts.*` imports together, removed stray blank line within import block
- `tests/runtime/test_contract_guards.py`: added `test_no_relative_import_from_dissolved_contracts_modules` — previous guard only caught absolute import strings, not `from .contracts import` within `runtime/` and `oracle/` packages
- `src/runtime/README.md`: updated stale reference to dissolved `contracts.py`; now points to canonical location `src/contracts/pipeline.py`
- Story File List: added `uv.lock` (was modified by `uv add --dev pytest` but undocumented)

**Final test run:** 139 passed (138 original + 1 new guard test), 0 failed

### File List

- `src/contracts/pipeline.py` (new)
- `src/contracts/oracle.py` (new)
- `src/contracts/ipc.py` (new)
- `src/contracts/__init__.py` (modified)
- `src/runtime/ticks.py` (modified)
- `src/runtime/utterance.py` (modified)
- `src/runtime/engine.py` (modified)
- `src/oracle/service.py` (modified)
- `src/oracle/providers.py` (modified)
- `src/runtime/workers/core.py` (modified)
- `src/runtime/contracts.py` (deleted)
- `src/oracle/contracts.py` (deleted)
- `tests/runtime/test_contract_guards.py` (modified)
- `tests/oracle/test_oracle_context_service.py` (modified)
- `pyproject.toml` (modified — added pytest pythonpath config and dev dependency)
- `uv.lock` (modified — updated by `uv add --dev pytest`)

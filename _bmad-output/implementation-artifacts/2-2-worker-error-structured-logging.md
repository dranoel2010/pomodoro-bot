# Story 2.2: Worker Error Structured Logging

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want worker errors surfaced in the same structured log stream as `PipelineMetrics` with the main process remaining alive and recoverable,
so that I can diagnose which worker failed and why without the daemon crashing and requiring a manual restart.

## Acceptance Criteria

1. **Given** an ML worker subprocess (STT, LLM, or TTS) raises an exception during an utterance cycle
   **When** the exception propagates to the main process
   **Then** the main process does not terminate — it catches the exception and logs a structured error entry
   **And** the structured error log entry appears at the same log level as `PipelineMetrics` output (`logger.info`)
   **And** the log entry identifies the failing worker and includes the exception message

2. **Given** a `WorkerCallTimeoutError` is raised
   **When** it is caught by the pipeline orchestration
   **Then** it is logged as a structured entry with `"event": "worker_timeout"` and the worker name
   **And** the system returns to an idle, ready-for-next-utterance state

3. **Given** a `WorkerCrashError` is raised
   **When** it is caught by the pipeline orchestration
   **Then** it is logged as a structured entry with `"event": "worker_crash"` and the worker name
   **And** the system returns to an idle, ready-for-next-utterance state

4. **Given** a `WorkerTaskError` is raised
   **When** it is caught by the pipeline orchestration
   **Then** it is logged as a structured entry with `"event": "worker_task_error"` and the worker name
   **And** the system returns to an idle, ready-for-next-utterance state

5. **Given** worker error logging is implemented
   **When** `uv run pytest tests/` is executed
   **Then** all error handling paths are covered by unit tests using worker stubs — no real subprocesses required

## Tasks / Subtasks

- [x] Add worker error imports and `_log_worker_error()` helper to `src/runtime/utterance.py` (AC: #1, #2, #3, #4)
  - [x] Add `import json` to the stdlib imports section (after existing `import logging` and `import time`)
  - [x] Add `from .workers.core import WorkerCallTimeoutError, WorkerCrashError, WorkerTaskError` after the `from contracts.pipeline import ...` line
  - [x] Add new helper function `_log_worker_error(event, error, *, logger, publish_idle_state)` — see Dev Notes for exact signature and body
  - [x] Add three specific `except` clauses for `WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError` **BEFORE** the existing `except (STTError, TTSError)` handler — see Dev Notes for exact placement

- [x] Create `tests/runtime/test_worker_error_logging.py` (AC: #2, #3, #4, #5)
  - [x] File must start with `from __future__ import annotations` (Epic 1 retro action item #1 — no exceptions)
  - [x] Use identical runtime package stub pattern as `test_utterance_state_flow.py` (see Dev Notes)
  - [x] Import `WorkerCallTimeoutError, WorkerCrashError, WorkerTaskError` from `runtime.workers.core` **BEFORE** the `patch.dict` context (see Dev Notes for why this ordering matters)
  - [x] Duplicate the `_build_llm_stub_modules()`, `_build_stt_stub_modules()`, `_build_tts_stub_modules()` functions from `test_utterance_state_flow.py` — identical copies
  - [x] Implement `_STTStub`, `_LLMStub`, `_TTSStub`, `_UIStub` stubs that accept an optional `error` to raise (see Dev Notes for exact stub design)
  - [x] Implement `_TranscriptionResultStub` for STT success path
  - [x] Test `test_worker_call_timeout_logs_structured_worker_timeout_event` — STT raises `WorkerCallTimeoutError`; assert `logger.info` was called with JSON containing `"event":"worker_timeout"` and the error message; assert `publish_idle_state` called once
  - [x] Test `test_worker_crash_logs_structured_worker_crash_event` — LLM raises `WorkerCrashError`; assert `"event":"worker_crash"` in structured log; assert `publish_idle_state` called once
  - [x] Test `test_worker_task_error_logs_structured_worker_task_error_event` — TTS raises `WorkerTaskError`; assert `"event":"worker_task_error"` in structured log; assert `publish_idle_state` called once
  - [x] Test `test_worker_error_main_process_does_not_crash` — verify `process_utterance` returns normally (no exception propagated) when worker raises `WorkerCrashError`
  - [x] Test `test_worker_error_log_is_valid_json_with_required_fields` — parse the emitted JSON, assert both `"event"` and `"message"` fields are present
  - [x] `if __name__ == "__main__": unittest.main()` entry point

- [x] Run full test suite and confirm all pass (AC: #5)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — all guard tests pass (no structural violations)
  - [x] `uv run pytest tests/runtime/test_worker_error_logging.py` — all new worker error tests pass
  - [x] `uv run pytest tests/` — all tests pass, zero regressions; expected count ≥ 167 (162 baseline + 5 new tests)

## Dev Notes

### Current State — What Exists in `utterance.py`

`src/runtime/utterance.py` already has:
- `except (STTError, TTSError) as error:` — calls `_publish_error()` which uses `logger.error()` (unstructured) and publishes `EVENT_ERROR + STATE_ERROR` to UI
- `except Exception as error:` — calls `_publish_error("LLM processing failed", ...)` — this currently catches ALL other exceptions including `WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError`
- `finally:` block that **always** emits `PipelineMetrics` JSON via `logger.info(metrics.to_json())`

**The problem**: Worker errors are currently silently swallowed by `except Exception`, logged informally via `logger.error()`, and the UI gets an error event. The AC requires:
1. Structured JSON log at `logger.info` level (same as `PipelineMetrics`)
2. No UI error event (just return to idle — the worker auto-restarts via `_ProcessWorker._restart_worker()`)

### Exact `utterance.py` Changes

**New import additions** (maintain existing import ordering: stdlib → third-party → local absolute → local relative):

```python
# Add to stdlib block (after `import time`):
import json

# Add after `from contracts.pipeline import LLMClient, STTClient, TTSClient`:
from .workers.core import WorkerCallTimeoutError, WorkerCrashError, WorkerTaskError
```

**New exception handlers — EXACT PLACEMENT in `process_utterance()`:**

The current except block structure (lines 123–133):
```python
    except (STTError, TTSError) as error:
        prefix = "Transcription failed" if isinstance(error, STTError) else "TTS playback failed"
        _publish_error(prefix, error, logger=logger, ui=ui, publish_idle_state=publish_idle_state)
    except Exception as error:
        _publish_error(
            "LLM processing failed",
            error,
            logger=logger,
            ui=ui,
            publish_idle_state=publish_idle_state,
        )
```

Replace with (worker-specific handlers BEFORE the existing ones):
```python
    except WorkerCallTimeoutError as error:
        _log_worker_error("worker_timeout", error, logger=logger, publish_idle_state=publish_idle_state)
    except WorkerCrashError as error:
        _log_worker_error("worker_crash", error, logger=logger, publish_idle_state=publish_idle_state)
    except WorkerTaskError as error:
        _log_worker_error("worker_task_error", error, logger=logger, publish_idle_state=publish_idle_state)
    except (STTError, TTSError) as error:
        prefix = "Transcription failed" if isinstance(error, STTError) else "TTS playback failed"
        _publish_error(prefix, error, logger=logger, ui=ui, publish_idle_state=publish_idle_state)
    except Exception as error:
        _publish_error(
            "LLM processing failed",
            error,
            logger=logger,
            ui=ui,
            publish_idle_state=publish_idle_state,
        )
```

**New helper function** (add after the existing `_publish_error()` helper):

```python
def _log_worker_error(
    event: str,
    error: Exception,
    *,
    logger: logging.Logger,
    publish_idle_state: Callable[[], None],
) -> None:
    entry = json.dumps({"event": event, "message": str(error)}, separators=(",", ":"))
    logger.info(entry)
    publish_idle_state()
```

**Why `logger.info()` not `logger.error()`:** The AC specifies worker errors appear "at the same log level as `PipelineMetrics` output". `PipelineMetrics` is emitted via `logger.info()`. The structured log stream must be parseable uniformly — mixing `error`-level and `info`-level output would complicate log consumers.

**Why no UI `EVENT_ERROR`:** Worker errors are self-healing — `_ProcessWorker._restart_worker()` is called by the worker itself before the exception reaches `process_utterance`. Publishing a UI error would be misleading (the worker is already recovering). The `publish_idle_state()` call is sufficient to reset UI state.

**Worker name is embedded in error message:** `_ProcessWorker` formats all error messages as `f"{self._name} worker timed out."` / `f"{self._name} worker crashed."` / `f"{self._name} task failed: ..."`. So `str(error)` for an STT timeout is `"STT worker timed out."`. The `"message"` field in the JSON implicitly identifies the failing worker.

**Structured log format:**
```
{"event":"worker_timeout","message":"STT worker timed out."}
{"event":"worker_crash","message":"LLM worker crashed."}
{"event":"worker_task_error","message":"TTS task failed: SomeError: details"}
```

### `WorkerError` Hierarchy (from `workers/core.py`)

```python
class WorkerError(RuntimeError): ...
class WorkerCallTimeoutError(WorkerError): ...  # worker did not respond within timeout
class WorkerCrashError(WorkerError): ...        # worker process exited unexpectedly
class WorkerTaskError(WorkerError): ...         # worker runtime raised during handle()
```

All are `RuntimeError` subclasses → currently swallowed by `except Exception`. None overlap with `STTError` or `TTSError`.

### Test File — Exact Import Bootstrap Pattern

The test must use **identical** bootstrap as `test_utterance_state_flow.py` with one critical addition: import `WorkerCallTimeoutError` etc. **before** the `patch.dict` context so they remain accessible after the context exits:

```python
from __future__ import annotations

import json
import logging
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Bootstrap runtime package (same pattern as test_utterance_state_flow.py)
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]  # type: ignore[attr-defined]
    sys.modules["runtime"] = _pkg

# Import worker error types BEFORE the patch.dict context.
# runtime.workers.core has no heavy native deps (only stdlib + contracts.ipc).
# By importing here, runtime.workers.core is added to sys.modules BEFORE patch.dict,
# so patch.dict will NOT remove it when the with-block exits.
from runtime.workers.core import WorkerCallTimeoutError, WorkerCrashError, WorkerTaskError
```

**Why the ordering matters:** `patch.dict(sys.modules, {...})` restores sys.modules to its state at context entry on exit — it removes any NEW keys added during the with-block. If `runtime.workers.core` were first imported inside the with-block (as a side effect of importing `runtime.utterance`), it would be removed on exit, potentially invalidating the error class references. Importing it before ensures it survives.

### Test Stub Design

```python
class _TranscriptionResultStub:
    def __init__(self, text: str = "stopp den timer", language: str = "de", confidence: float | None = 0.9):
        self.text = text
        self.language = language
        self.confidence = confidence


class _STTStub:
    """Returns a successful transcription result or raises a given worker error."""
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    def transcribe(self, utterance: object) -> _TranscriptionResultStub:
        if self._error is not None:
            raise self._error
        return _TranscriptionResultStub()


class _LLMStub:
    """Returns a fixed LLM response or raises a given worker error."""
    def __init__(
        self,
        *,
        error: Exception | None = None,
        response: dict | None = None,
    ) -> None:
        self._error = error
        self._response = response or {"assistant_text": "Ich habe das verstanden.", "tool_call": None}

    def run(self, prompt: str, *, env: object = None, extra_context: object = None, max_tokens: object = None) -> dict:
        if self._error is not None:
            raise self._error
        return dict(self._response)

    @property
    def last_tokens(self) -> int:
        return 0


class _TTSStub:
    """Speaks silently or raises a given worker error."""
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    def speak(self, text: str) -> None:
        if self._error is not None:
            raise self._error


class _UIStub:
    def publish(self, event_type: str, **payload: object) -> None:
        pass

    def publish_state(self, state: str, *, message: object = None, **payload: object) -> None:
        pass
```

### Test Helper Pattern

Use `MagicMock(spec=logging.Logger)` to capture all `logger.info` calls, then parse each call arg for the expected JSON event:

```python
def _find_worker_event(info_call_args: list[str], event: str) -> dict | None:
    """Return the first dict found in info calls where data["event"] == event."""
    for msg in info_call_args:
        try:
            data = json.loads(msg)
            if isinstance(data, dict) and data.get("event") == event:
                return data
        except (ValueError, TypeError):
            pass
    return None
```

Access `MagicMock` call args via:
```python
mock_logger = MagicMock(spec=logging.Logger)
# ... after process_utterance call:
info_call_args = [call.args[0] for call in mock_logger.info.call_args_list if call.args]
```

**Note:** `process_utterance` makes several `logger.info` calls (transcription status, LLM fast-path, etc.) before reaching the error path. The `finally` block also calls `logger.info(metrics.to_json())` (PipelineMetrics) which is always emitted. `_find_worker_event` handles multiple calls correctly by filtering for the specific event key.

### Test: TTS Worker Error — Prerequisites

For `WorkerTaskError` raised in TTS, the following conditions must hold:
1. STT must succeed (use `_STTStub()` with no error)
2. LLM must succeed with a non-empty `assistant_text` (use `_LLMStub()` with default response)
3. `speech_service` must not be None (pass `_TTSStub(error=WorkerTaskError(...))`)
4. `llm_fast_path_enabled=False` to skip the fast-path and force the LLM path

In `process_utterance`, `speech_service.speak()` is only called when `assistant_text` is truthy **and** `speech_service is not None`. The `_LLMStub` default response has `"assistant_text": "Ich habe das verstanden."` — non-empty, satisfying both conditions.

### Guard Test Compliance — No New Violations

After these changes, run `uv run pytest tests/runtime/test_contract_guards.py`:
- **`test_worker_modules_do_not_use_mutable_process_instance_globals`** — checks `workers/llm.py`, `workers/stt.py`, `workers/tts.py`. Not touched.
- **`test_runtime_signatures_do_not_use_dict_object_contracts`** — checks `utterance.py`. The new `_log_worker_error()` helper uses typed parameters (`str`, `Exception`, `logging.Logger`, `Callable`). No `dict[str, object]` added. ✓
- **`ContractsConsolidationGuards`** — not affected. ✓
- **`LlmModuleBoundaryGuards`** — not affected. ✓
- **`DispatchPatternGuards`** — not affected. ✓

### Architecture Compliance Checklist (from Epic 1 Retro)

- **`from __future__ import annotations` on ALL modified/created files** — Epic 1 retro action item #1. This story touches `utterance.py` (already has it) and creates `test_worker_error_logging.py` (must be first line). No exceptions.
- **No `dict[str, object]` in `utterance.py`** — enforced by guard test. The new `_log_worker_error()` uses typed parameters only.
- **No module-level mutable state added** — `_log_worker_error` is a pure function with no module-level state.
- **`import json` at module level** — correct; `json` is stdlib with no initialization cost.

### `json` Import — Already Used in `llm/types.py`, New to `utterance.py`

`utterance.py` currently does NOT import `json`. Adding it is correct and required for `_log_worker_error()`. It's a stdlib module — no external dependency, no test stub needed. The `finally` block's `PipelineMetrics.to_json()` already uses `json` internally (in `llm/types.py`), but that's in a different module.

### `from .workers.core` — Import Safety in Test Context

`runtime/workers/core.py` imports:
```python
from contracts.ipc import _RequestEnvelope, _ResponseEnvelope
```

`contracts/ipc.py` imports only `dataclasses` and `typing` (stdlib). No heavy native deps. Safe to import in any test context without stubs.

### Previous Story Intelligence (from Story 2.1 completion notes)

- **Test baseline: 162 tests** (154 original + 6 new PipelineMetrics tests + 2 code-review fix tests)
- **Pattern established**: new test files for new capabilities (don't add tests to `test_utterance_state_flow.py`)
- **`from __future__ import annotations` was a recurring review finding in Epic 1** — Epic 1 retro elevated this to an action item. Story 2.1's review added it to `test_worker_context_manager.py`. For this story: verify the new test file starts with it.
- **`MagicMock` vs hand-written stubs**: Story 2.1 used hand-written stubs in `test_utterance_state_flow.py` for structured call capture. For worker error logging tests, `MagicMock(spec=logging.Logger)` is appropriate for logger capture since we don't need structured call records beyond `call_args_list`.
- **`PipelineMetrics` stub in `test_utterance_state_flow.py`**: The PipelineMetrics stub (in `_build_llm_stub_modules()`) returns minimal JSON from `to_json()`. The new test file must duplicate this stub exactly — it will be exercised in the `finally` block even during worker error tests.

### Project Structure Notes

Files to modify:
- `src/runtime/utterance.py` — add `import json`, add worker error imports, add 3 new `except` clauses, add `_log_worker_error()` helper

Files to create:
- `tests/runtime/test_worker_error_logging.py` — 5 new unit tests covering all 3 error types and main-process survival

No new source files in `src/`. No changes to `workers/core.py` — the error types are already defined there.

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 2.2 acceptance criteria (FR23, NFR-R1)
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "Error communication: Worker exceptions (`WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError`) surface in the structured log stream at the same level as `PipelineMetrics` output"
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "PipelineMetrics — Phase 1 Decision: Structured logger only"; `logger.info()` is the approved output channel
- Project context: `_bmad-output/project-context.md` — Rule 5 "Worker Modules — No Mutable Module-Level State"; Rule 6 "Runtime Signatures — No `dict[str, object]`"; Rule 7 "Dataclass Style"
- Previous story: `_bmad-output/implementation-artifacts/2-1-pipelinemetrics-typed-dataclass-structured-json-log-emission.md` — test baseline 162, `PipelineMetrics` stub pattern, `MagicMock` vs hand-written stubs
- Retrospective: `_bmad-output/implementation-artifacts/epic-1-retro-2026-03-01.md` — Action #1: `from __future__ import annotations` on ALL modified files; test files are first-class under compliance rules
- Source: `src/runtime/utterance.py` — existing exception handlers at lines 123–133; `_publish_error()` helper at lines 154–168
- Source: `src/runtime/workers/core.py` — `WorkerError` hierarchy at lines 14–36; `_ProcessWorker.call()` exception re-raising at lines 362–367
- Source: `tests/runtime/test_utterance_state_flow.py` — stub module builders and runtime package bootstrap pattern to duplicate exactly

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No debug issues encountered — clean implementation, all tests passed first run.

### Completion Notes List

- Added `import json` to stdlib imports in `src/runtime/utterance.py`
- Added `from .workers.core import WorkerCallTimeoutError, WorkerCrashError, WorkerError, WorkerTaskError` relative import (includes base `WorkerError` for catchall handler)
- Added `_log_worker_error()` helper after `_publish_error()` — emits compact JSON via `logger.info()` and calls `publish_idle_state()`, matching AC requirement of same log level as `PipelineMetrics`
- Inserted four typed `except` clauses BEFORE the existing `except (STTError, TTSError)` handler: `WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError` (specific), plus `WorkerError` base class (catchall for `WorkerInitError`, `WorkerClosedError`, and future subtypes)
- Created `tests/runtime/test_worker_error_logging.py` with 6 unit tests covering all three story error types, base-class catchall, main-process survival, and JSON field validation
- Worker error types imported BEFORE `patch.dict` context to ensure `runtime.workers.core` remains in `sys.modules` after context exit — prevents class identity mismatch
- `_UIStub` updated to track error events; all tests assert `ui_stub.error_events == []` (no UI error event published on worker failures)
- All 168 tests pass (162 baseline + 6 new), zero regressions, all contract guard tests pass

### File List

- `src/runtime/utterance.py` (modified)
- `tests/runtime/test_worker_error_logging.py` (created)

## Change Log

- 2026-03-01: Implemented worker error structured logging — added `_log_worker_error()` helper and three typed except clauses to `utterance.py`; created `test_worker_error_logging.py` with 5 new unit tests (Story 2.2)
- 2026-03-01: Code review fixes — added `WorkerError` base class handler for `WorkerInitError`/`WorkerClosedError` coverage; added `_UIStub` error tracking and `error_events` assertions to all tests; added `test_worker_base_error_logs_structured_worker_error_event` test; 168 tests total

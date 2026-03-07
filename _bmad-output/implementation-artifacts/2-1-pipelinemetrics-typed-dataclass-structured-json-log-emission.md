# Story 2.1: PipelineMetrics Typed Dataclass & Structured JSON Log Emission

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want a typed `PipelineMetrics` dataclass emitted per utterance as structured JSON to the log output,
so that I can verify performance gates mechanically from log output and diagnose which pipeline stage is slow without printf debugging.

## Acceptance Criteria

1. **Given** an utterance cycle completes
   **When** `PipelineMetrics` is emitted
   **Then** it is a `@dataclass(frozen=True, slots=True)` with fields: `stt_ms: int`, `llm_ms: int`, `tts_ms: int`, `tokens: int`, `tok_per_sec: float`, `e2e_ms: int`
   **And** it is emitted synchronously — no buffering, no batch aggregation — immediately after the utterance cycle completes
   **And** `logger.info(metrics.to_json())` produces exactly: `{"event":"pipeline_metrics","stt_ms":N,"llm_ms":N,"tts_ms":N,"tokens":N,"tok_per_sec":F,"e2e_ms":N}`

2. **Given** `PipelineMetrics` is defined in `llm/types.py`
   **When** a developer writes a unit test for metrics emission
   **Then** the test can assert the correct JSON output without executing an end-to-end utterance cycle
   **And** the test requires no hardware, no model files, and no real subprocess spawn

3. **Given** a fast-path utterance bypasses LLM inference
   **When** `PipelineMetrics` is emitted
   **Then** `llm_ms` is `0` and `tokens` is `0` — fast-path bypasses LLM cleanly without leaving metric fields undefined
   **And** `tok_per_sec` is `0.0`

## Tasks / Subtasks

- [x] Add `LLMResult` and `PipelineMetrics` to `src/llm/types.py` (AC: #1, #2)
  - [x] Add `@dataclass(frozen=True, slots=True) class LLMResult` with fields `response: StructuredResponse` and `tokens: int` — IPC result carrier for subprocess → main-process token transfer
  - [x] Add `@dataclass(frozen=True, slots=True) class PipelineMetrics` with fields `stt_ms: int`, `llm_ms: int`, `tts_ms: int`, `tokens: int`, `tok_per_sec: float`, `e2e_ms: int`
  - [x] Implement `to_json(self) -> str` on `PipelineMetrics` using `json.dumps({...}, separators=(",", ":"))` with key `"event": "pipeline_metrics"` — compact JSON, no spaces

- [x] Add `last_tokens: int` property to `LLMClient` Protocol in `src/contracts/pipeline.py` (AC: #1)
  - [x] Add `@property` method `last_tokens(self) -> int: ...` to `LLMClient`
  - [x] Keep the import block: `from llm.types import EnvironmentContext, StructuredResponse` (TYPE_CHECKING guard is already correct)

- [x] Update `_LLMProcess.handle()` in `src/runtime/workers/llm.py` to return `LLMResult` (AC: #1)
  - [x] Add `LLMResult` as a runtime import at module top level: `from llm.types import LLMResult` (runtime import — used in `handle()` at runtime, not TYPE_CHECKING guard)
  - [x] Change `handle()` to call `self._llm.run()`, then read `self._llm.last_tokens`, then `return LLMResult(response=response, tokens=self._llm.last_tokens)`
  - [x] Add `_last_tokens: int = 0` instance variable to `LLMWorker.__init__`
  - [x] Change `LLMWorker.run()` to cast result as `LLMResult`, store `self._last_tokens = result.tokens`, return `result.response`
  - [x] Add `last_tokens(self) -> int` property to `LLMWorker` returning `self._last_tokens`

- [x] Add `last_tokens` property to `PomodoroAssistantLLM` in `src/llm/service.py` (AC: #1)
  - [x] Add `self._last_tokens: int = 0` in `__init__`
  - [x] At end of `run()` method (before the `return parser.parse(...)` line), store: `self._last_tokens = completion_tokens_derived if isinstance(completion_tokens_derived, int) else 0`
  - [x] Add `@property def last_tokens(self) -> int: return self._last_tokens`

- [x] Emit `PipelineMetrics` in `src/runtime/utterance.py` (AC: #1, #3)
  - [x] Add `PipelineMetrics` to the `llm.types` import: `from llm.types import EnvironmentContext, PipelineMetrics, StructuredResponse, ToolCall`
  - [x] Add `llm_tokens: int = 0` to the local variable block at the top of `process_utterance()` (alongside `fast_path_used = False` etc.)
  - [x] After `llm_response = assistant_llm.run(...)` call (non-fast-path branch), add: `llm_tokens = assistant_llm.last_tokens`
  - [x] In the `finally:` block, replace the existing `logger.info("Utterance pipeline metrics: ...")` call with `PipelineMetrics` construction and `logger.info(metrics.to_json())`
  - [x] Fast-path: `llm_ms=0`, `tokens=0`, `tok_per_sec=0.0` (because `llm_tokens` stays 0 and `llm_duration_seconds` stays None)
  - [x] `tok_per_sec` computation: `round(llm_tokens / llm_duration_seconds, 2) if (llm_tokens > 0 and llm_duration_seconds is not None and llm_duration_seconds > 0.0) else 0.0`
  - [x] Remove `_fmt_duration_ms` helper if it becomes unused after the refactor (check usages first)

- [x] Create `tests/llm/test_pipeline_metrics.py` (AC: #2, #3)
  - [x] Test `to_json()` produces `"event": "pipeline_metrics"` key
  - [x] Test all six fields appear in the JSON output with correct values
  - [x] Test fast-path zeroed values: `llm_ms=0`, `tokens=0`, `tok_per_sec=0.0`
  - [x] Test `to_json()` produces valid JSON (no extra spaces in compact form)
  - [x] Test `PipelineMetrics` is frozen (mutation raises `FrozenInstanceError`)
  - [x] File must start with `from __future__ import annotations` (project mandate)
  - [x] Class must inherit `unittest.TestCase` with `if __name__ == "__main__": unittest.main()` entry point

- [x] Fix stale path reference in `_bmad-output/project-context.md` (retro action item #TD-1)
  - [x] Replace `stt/stt.py` reference with `stt/transcription.py` in the Project Structure section (line ~74)

- [x] Run full test suite and confirm all pass (AC: #1, #2, #3)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — all guard tests pass (no structural violations)
  - [x] `uv run pytest tests/llm/test_pipeline_metrics.py` — all new PipelineMetrics tests pass
  - [x] `uv run pytest tests/` — all tests pass, zero regressions; expected count ≥ 159 (154 + 5 new)

## Dev Notes

### Current State — What Exists

`utterance.py` already tracks per-stage durations:
- `stt_duration_seconds: float | None`
- `llm_duration_seconds: float | None`
- `tts_duration_seconds: float | None`
- `fast_path_duration_seconds: float | None`
- `fast_path_used: bool`

The current `finally:` block emits an **informal, non-machine-readable log line**:
```python
logger.info(
    "Utterance pipeline metrics: total_ms=%d stt_ms=%s llm_ms=%s tts_ms=%s fast_path=%s fast_path_ms=%s transcript_chars=%d",
    ...
)
```

This **must be replaced** with `logger.info(metrics.to_json())` using the new `PipelineMetrics` dataclass. The existing informal metrics log is the _only_ log line in the `finally:` block; simply replace it.

`_fmt_duration_ms()` is a helper used only by the old informal metrics log. After replacing the log line with `PipelineMetrics`, check if `_fmt_duration_ms()` is still referenced anywhere in the file. If not, delete it.

### Exact IPC Token Flow

The LLM worker is an out-of-process `_ProcessWorker`. Token counts are produced inside the spawned subprocess by `PomodoroAssistantLLM.run()`. To expose them to the main process, a two-dataclass approach is used:

1. **`LLMResult`** (new, in `llm/types.py`) — IPC result carrier, returned by `_LLMProcess.handle()`:
   ```python
   @dataclass(frozen=True, slots=True)
   class LLMResult:
       response: StructuredResponse
       tokens: int
   ```

2. The subprocess `_LLMProcess.handle()` currently returns `self._llm.run(...)` (a `StructuredResponse`). Change it to:
   ```python
   def handle(self, payload: object) -> object:
       if not isinstance(payload, LLMPayload):
           raise ValueError(f"Expected LLMPayload, got {type(payload).__name__}")
       response = self._llm.run(
           payload.user_prompt,
           env=payload.env,
           extra_context=payload.extra_context,
           max_tokens=payload.max_tokens,
       )
       return LLMResult(response=response, tokens=self._llm.last_tokens)
   ```

3. `LLMWorker.run()` currently does `return cast("StructuredResponse", self._worker.call(payload))`. Change to:
   ```python
   def run(self, user_prompt: str, *, env=None, extra_context=None, max_tokens=None) -> StructuredResponse:
       payload = LLMPayload(
           user_prompt=user_prompt,
           env=env,
           extra_context=extra_context,
           max_tokens=max_tokens,
       )
       result = cast("LLMResult", self._worker.call(payload))
       self._last_tokens = result.tokens
       return result.response
   ```

4. `LLMResult` is pickled across the process boundary (Python multiprocessing). `@dataclass(frozen=True, slots=True)` dataclasses pickle correctly via `__reduce__` — no special handling required.

### `PomodoroAssistantLLM.last_tokens` — Where to Store

In `service.py`, `completion_tokens_derived` is computed after `self._backend.complete()`. It can be `None` (when token accounting data is unavailable). Store as int:

```python
# In run(), after computing completion_tokens_derived:
self._last_tokens = completion_tokens_derived if isinstance(completion_tokens_derived, int) else 0
```

Add to `__init__`: `self._last_tokens: int = 0`

Add property:
```python
@property
def last_tokens(self) -> int:
    return self._last_tokens
```

The exact insertion point in `service.py` `run()` method: after the two branches that compute `completion_tokens_derived` (both the `usage is not None` branch and the `else` branch), and before `self._logger.info("LLM completion: ...")`. Specifically, `completion_tokens_derived` is always computed by that point in the function, so store it immediately after.

### `utterance.py` — Exact finally Block Target

Current `finally:` block (lines 133–143):
```python
finally:
    total_duration_seconds = time.perf_counter() - pipeline_started_at
    logger.info(
        "Utterance pipeline metrics: total_ms=%d stt_ms=%s llm_ms=%s tts_ms=%s fast_path=%s fast_path_ms=%s transcript_chars=%d",
        round(total_duration_seconds * 1000),
        _fmt_duration_ms(stt_duration_seconds),
        _fmt_duration_ms(llm_duration_seconds),
        _fmt_duration_ms(tts_duration_seconds),
        fast_path_used,
        _fmt_duration_ms(fast_path_duration_seconds),
        len(transcript_text),
    )
```

Replace with:
```python
finally:
    total_duration_seconds = time.perf_counter() - pipeline_started_at
    _llm_ms = round(llm_duration_seconds * 1000) if (not fast_path_used and llm_duration_seconds is not None) else 0
    _tokens = llm_tokens if not fast_path_used else 0
    _tok_per_sec = (
        round(_tokens / llm_duration_seconds, 2)
        if (_tokens > 0 and llm_duration_seconds is not None and llm_duration_seconds > 0.0)
        else 0.0
    )
    metrics = PipelineMetrics(
        stt_ms=round(stt_duration_seconds * 1000) if stt_duration_seconds is not None else 0,
        llm_ms=_llm_ms,
        tts_ms=round(tts_duration_seconds * 1000) if tts_duration_seconds is not None else 0,
        tokens=_tokens,
        tok_per_sec=_tok_per_sec,
        e2e_ms=round(total_duration_seconds * 1000),
    )
    logger.info(metrics.to_json())
```

After this change, check whether `_fmt_duration_ms` is still referenced elsewhere in `utterance.py`. If not used, delete it.

### PipelineMetrics.to_json() — Exact Format

```python
def to_json(self) -> str:
    return json.dumps(
        {
            "event": "pipeline_metrics",
            "stt_ms": self.stt_ms,
            "llm_ms": self.llm_ms,
            "tts_ms": self.tts_ms,
            "tokens": self.tokens,
            "tok_per_sec": self.tok_per_sec,
            "e2e_ms": self.e2e_ms,
        },
        separators=(",", ":"),
    )
```

This produces compact JSON: `{"event":"pipeline_metrics","stt_ms":100,"llm_ms":500,"tts_ms":200,"tokens":42,"tok_per_sec":84.0,"e2e_ms":800}`

Note: `json` is already imported in `llm/types.py` — no new import needed.

### LLMClient Protocol Extension

`src/contracts/pipeline.py` — current:
```python
class LLMClient(Protocol):
    def run(
        self,
        user_prompt: str,
        *,
        env: EnvironmentContext | None = None,
        extra_context: str | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResponse:
        ...
```

Add `last_tokens` property after `run()`:
```python
    @property
    def last_tokens(self) -> int:
        ...
```

The `TYPE_CHECKING` guard already imports `StructuredResponse` — no new imports needed for `last_tokens`.

### Test File — `tests/llm/test_pipeline_metrics.py`

`tests/llm/__init__.py` already exists — no need to create it.

`PipelineMetrics` lives in `llm/types.py`. Direct import (no `sys.modules` stub needed — `llm/types.py` has no heavy native dependencies):

```python
from __future__ import annotations

import json
import unittest

from llm.types import PipelineMetrics


class PipelineMetricsTests(unittest.TestCase):
    def test_to_json_event_key(self) -> None:
        metrics = PipelineMetrics(stt_ms=100, llm_ms=500, tts_ms=200, tokens=42, tok_per_sec=84.0, e2e_ms=800)
        data = json.loads(metrics.to_json())
        self.assertEqual("pipeline_metrics", data["event"])

    def test_to_json_all_fields_present(self) -> None:
        metrics = PipelineMetrics(stt_ms=100, llm_ms=500, tts_ms=200, tokens=42, tok_per_sec=84.0, e2e_ms=800)
        data = json.loads(metrics.to_json())
        self.assertEqual(100, data["stt_ms"])
        self.assertEqual(500, data["llm_ms"])
        self.assertEqual(200, data["tts_ms"])
        self.assertEqual(42, data["tokens"])
        self.assertEqual(84.0, data["tok_per_sec"])
        self.assertEqual(800, data["e2e_ms"])

    def test_to_json_fast_path_zeroed_fields(self) -> None:
        metrics = PipelineMetrics(stt_ms=50, llm_ms=0, tts_ms=150, tokens=0, tok_per_sec=0.0, e2e_ms=200)
        data = json.loads(metrics.to_json())
        self.assertEqual(0, data["llm_ms"])
        self.assertEqual(0, data["tokens"])
        self.assertEqual(0.0, data["tok_per_sec"])

    def test_to_json_is_valid_json(self) -> None:
        metrics = PipelineMetrics(stt_ms=100, llm_ms=500, tts_ms=200, tokens=42, tok_per_sec=84.0, e2e_ms=800)
        result = metrics.to_json()
        parsed = json.loads(result)  # must not raise
        self.assertIsInstance(parsed, dict)

    def test_to_json_compact_no_spaces(self) -> None:
        metrics = PipelineMetrics(stt_ms=1, llm_ms=2, tts_ms=3, tokens=4, tok_per_sec=2.0, e2e_ms=6)
        result = metrics.to_json()
        self.assertNotIn(" ", result)

    def test_metrics_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError
        metrics = PipelineMetrics(stt_ms=100, llm_ms=500, tts_ms=200, tokens=42, tok_per_sec=84.0, e2e_ms=800)
        with self.assertRaises(FrozenInstanceError):
            metrics.stt_ms = 999  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
```

### Architecture Compliance

- `from __future__ import annotations` required on ALL modified/created files, including the new test file — no exceptions (retro lesson #1 from Epic 1)
- `@dataclass(frozen=True, slots=True)` on both `LLMResult` and `PipelineMetrics` — project mandate for all high-frequency value objects
- No `dict[str, object]` in `utterance.py` signatures — contract guard enforced
- No new module-level mutable state in worker files — contract guard enforced
- `json` is already imported in `llm/types.py` — no new stdlib import needed for `to_json()`
- `LLMResult` must be importable in the subprocess (`workers/llm.py` imports it inside `_LLMProcess.handle()` via `TYPE_CHECKING` guard — use a deferred import inside `handle()` or add to the TYPE_CHECKING block)

**Note on `LLMResult` import in workers/llm.py:** The `_LLMProcess.handle()` method uses `LLMPayload` (which is defined in the same file). `LLMResult` needs to be importable inside the subprocess. Since `workers/llm.py` already has `TYPE_CHECKING` guard for `from llm.types import EnvironmentContext, StructuredResponse`, add `LLMResult` there too. The runtime import inside `handle()` uses `LLMResult` at runtime (not just type-check time), so it must also be imported at runtime in `handle()` or at module level. **Use a direct runtime import at module top level (not in TYPE_CHECKING guard)** for `LLMResult` in `workers/llm.py`:

```python
from llm.types import LLMResult, LLMPayload  # runtime import — used in handle()
```

Wait — `LLMPayload` is already defined in `workers/llm.py` itself (it's a local class). `LLMResult` needs to be imported from `llm.types`. Since `workers/llm.py` already imports from `llm.types` under `TYPE_CHECKING`, add a **runtime import** for `LLMResult` at module top level in `workers/llm.py`.

Actually, looking at the current `workers/llm.py` more carefully: it has no direct top-level imports from `llm.types` — only the `TYPE_CHECKING` guard. The `handle()` method runs inside the spawned subprocess, which has access to all of `src/` via the spawn initialization. So `LLMResult` is safely importable in the subprocess. Add it to the top of the file **outside** the `TYPE_CHECKING` block (since it's used at runtime):

```python
# At module top level, after existing imports, before TYPE_CHECKING block:
from llm.types import LLMResult
```

This is safe because `llm/types.py` has no heavy dependencies — it only imports `json`, `datetime`, `re`, `dataclasses`, and `contracts.tool_contract`.

### Guard Test Compliance

Run `uv run pytest tests/runtime/test_contract_guards.py` after changes. Key checks:
- **`RuntimeContractGuards`**: worker modules must not have `global _*` or `_*_INSTANCE` patterns. Adding `self._last_tokens` to `LLMWorker` is an **instance** variable, not a module global — passes.
- **`ContractsConsolidationGuards`**: confirms old `runtime/contracts.py` is dissolved. Not affected by this story.
- **`LlmModuleBoundaryGuards`**: checks LLM file boundaries. Adding `last_tokens` property to `service.py` doesn't violate boundaries (it's still orchestration logic). `LLMResult` in `types.py` is a result type — not parsing logic. Passes.
- **`DispatchPatternGuards`**: match/case in dispatch.py. Not affected.

### Project Structure Notes

Files to modify:
- `src/llm/types.py` — add `LLMResult` and `PipelineMetrics`
- `src/contracts/pipeline.py` — add `last_tokens` property to `LLMClient`
- `src/runtime/workers/llm.py` — `_LLMProcess.handle()` returns `LLMResult`; `LLMWorker.run()` unpacks it; new `last_tokens` property
- `src/llm/service.py` — store `_last_tokens` after `run()`; expose `last_tokens` property
- `src/runtime/utterance.py` — add `llm_tokens: int = 0` variable; read `assistant_llm.last_tokens`; replace `finally` block with `PipelineMetrics` emission
- `_bmad-output/project-context.md` — fix stale `stt/stt.py` reference → `stt/transcription.py`

Files to create:
- `tests/llm/test_pipeline_metrics.py` — direct unit tests for `PipelineMetrics` dataclass

No new source files in `src/` — only modifications to existing modules.

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 2.1 acceptance criteria (FR21, FR22, NFR-P3, NFR-T3)
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "PipelineMetrics — Phase 1 Decision: Structured logger only"; "Data Architecture"; "Data Flow" diagram; "Format Patterns — Structured Log Format (PipelineMetrics)"
- Project context: `_bmad-output/project-context.md` — "Dataclass Style", "Stub Pattern for Heavy Native Dependencies", "Worker Tests — Always Patch `_ProcessWorker`"
- Retrospective: `_bmad-output/implementation-artifacts/epic-1-retro-2026-03-01.md` — Action item: "from __future__ import annotations must be verified on ALL modified files"; Technical debt: stale `stt/stt.py` reference in project-context.md
- Source: `src/llm/types.py` — existing `StructuredResponse`, `EnvironmentContext`; `json` already imported
- Source: `src/runtime/utterance.py` — existing timing variables, `fast_path_used` flag, current informal metrics log in `finally` block
- Source: `src/runtime/workers/llm.py` — `_LLMProcess.handle()` returns `StructuredResponse` today; `LLMWorker.run()` casts via `cast()`
- Source: `src/llm/service.py` — `completion_tokens_derived` computed from `usage.derived_completion_tokens`
- Source: `src/contracts/pipeline.py` — current `LLMClient` Protocol definition
- Test baseline: 154 tests pass (confirmed by Story 1.5 completion notes)
- Architecture spec log format: `{"event": "pipeline_metrics", "stt_ms": N, "llm_ms": N, "tts_ms": N, "tokens": N, "tok_per_sec": F, "e2e_ms": N}` [Source: architecture.md#Format Patterns]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Implemented `LLMResult` and `PipelineMetrics` frozen dataclasses in `src/llm/types.py`. `PipelineMetrics.to_json()` produces compact JSON with `"event":"pipeline_metrics"` and all 6 metric fields.
- Extended `LLMClient` Protocol in `src/contracts/pipeline.py` with `last_tokens: int` property.
- Updated `_LLMProcess.handle()` in `src/runtime/workers/llm.py` to return `LLMResult` (IPC carrier). Added `_last_tokens` state and `last_tokens` property to `LLMWorker`.
- Added `_last_tokens` storage and `last_tokens` property to `PomodoroAssistantLLM` in `src/llm/service.py`. Token count stored after each `run()` completion.
- Replaced informal metrics log in `src/runtime/utterance.py` `finally:` block with typed `PipelineMetrics` emission. Removed `_fmt_duration_ms` helper (no longer used). Fast-path correctly emits `llm_ms=0`, `tokens=0`, `tok_per_sec=0.0`.
- Created `tests/llm/test_pipeline_metrics.py` with 6 unit tests covering all ACs. No hardware, no subprocess, no model files required.
- Updated test stubs in `test_utterance_state_flow.py` (added `PipelineMetrics` stub) and `test_worker_context_manager.py` (updated mock to return `LLMResult`, added `last_tokens` assertion).
- Fixed stale `stt/stt.py` → `stt/transcription.py` reference in `_bmad-output/project-context.md`.
- Full test suite: **160 passed** (154 baseline + 6 new), 0 failures, 0 regressions.

### File List

- `src/llm/types.py` — added `LLMResult` and `PipelineMetrics` dataclasses with `to_json()`
- `src/contracts/pipeline.py` — added `last_tokens` property to `LLMClient` Protocol
- `src/runtime/workers/llm.py` — runtime import of `LLMResult`; `_LLMProcess.handle()` returns `LLMResult`; `LLMWorker` gains `_last_tokens` state and `last_tokens` property
- `src/llm/service.py` — `PomodoroAssistantLLM` gains `_last_tokens` storage and `last_tokens` property
- `src/runtime/utterance.py` — imports `PipelineMetrics`; adds `llm_tokens` variable; reads `assistant_llm.last_tokens`; replaces `finally` block with `PipelineMetrics` emission; removes `_fmt_duration_ms`
- `tests/llm/test_pipeline_metrics.py` — new file: 6 unit tests for `PipelineMetrics`
- `tests/runtime/test_utterance_state_flow.py` — added `PipelineMetrics` stub and `last_tokens` property to `_AssistantLLMStub`
- `tests/runtime/test_worker_context_manager.py` — updated `test_llm_worker_run_uses_typed_payload` to use `LLMResult` mock and assert `last_tokens`; added `from __future__ import annotations` (review fix H1)
- `tests/runtime/test_utterance_state_flow.py` — tightened `_AssistantLLMStub.run()` to keyword-only `env` (review fix L3)
- `_bmad-output/project-context.md` — fixed stale `stt/stt.py` → `stt/transcription.py`

## Change Log

- 2026-03-01: Story 2.1 implementation complete. Added `LLMResult` IPC carrier and `PipelineMetrics` typed dataclass. Replaced informal metrics log with structured JSON emission. Extended `LLMClient` Protocol with `last_tokens`. Token count flows: `PomodoroAssistantLLM` → `_LLMProcess` → `LLMWorker` → `process_utterance`. 6 new unit tests added; all 160 tests pass.
- 2026-03-01: Code review complete (adversarial). Fixes applied — H1: added `from __future__ import annotations` to `test_worker_context_manager.py`; M1: staged `test_pipeline_metrics.py`; M2: added `LLMResult` pickle round-trip and frozen tests (2 new tests); L1: fixed PEP 8 E302 blank line in `workers/llm.py`; L2: corrected task description for `LLMResult` import location; L3: tightened `_AssistantLLMStub.run()` keyword-only signature. All 162 tests pass.

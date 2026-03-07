# Story 1.5: Hardware-Free Test Suite Verification

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want the complete test suite to pass without physical audio hardware, ML model files, wake-word model files, or network access,
so that I can run `uv run pytest tests/` on any development machine and trust the result as a valid regression baseline.

## Acceptance Criteria

1. **Given** the test suite is run on a machine with no Raspberry Pi hardware, no GGUF model files, no `.ppn`/`.pv` wake-word files, and no network connection
   **When** `uv run pytest tests/` is executed
   **Then** all tests pass with zero failures and zero errors
   **And** no test attempts to load a real llama-cpp-python, faster-whisper, piper, or pvporcupine model

2. **Given** each ML worker has a public Protocol-backed interface (`STTClient`, `LLMClient`, `TTSClient`)
   **When** a developer writes a test for any module that depends on an ML worker
   **Then** the worker can be replaced with a `sys.modules` stub or Protocol-conforming test double — no real subprocess spawn is required
   **And** the test double is sufficient to exercise the full logic of the module under test

3. **Given** all structural changes from Stories 1.1–1.4 are complete
   **When** `uv run pytest tests/` is executed
   **Then** the voice pipeline integration behaviour (FR1–5 sequential execution, FR6 fast-path routing) is verified by existing tests without hardware
   **And** the WebSocket UI event/state constants (FR33–35) are verified by existing tests using `src/contracts/ui_protocol.py` constants — no inline strings
   **And** the guard tests in `tests/runtime/test_contract_guards.py` all pass, enforcing all architectural invariants established in this epic

## Tasks / Subtasks

- [x] Update `tests/runtime/test_utterance_state_flow.py` to use ui_protocol constants (AC: #3)
  - [x] Add import: `from contracts.ui_protocol import EVENT_ASSISTANT_REPLY, STATE_REPLYING` at the top of the file (after sys.modules setup, before imports from runtime)
  - [x] Replace inline string `"replying"` in assertion → `STATE_REPLYING`
  - [x] Replace inline string `"assistant_reply"` in assertion filter → `EVENT_ASSISTANT_REPLY`
  - [x] Update `_AssistantLLMStub` to add `run_call_count: int = 0` and increment in `run()` so fast-path test can assert LLM was NOT called
  - [x] Add new test: `test_process_utterance_fast_path_bypasses_llm` — see Dev Notes for exact implementation

- [x] Update `tests/runtime/test_ticks_state_flow.py` to use ui_protocol constants (AC: #3)
  - [x] Add `from __future__ import annotations` as the very first line of the file (currently missing — project mandate: every module must begin with this import, no exceptions)
  - [x] Add import: `from contracts.ui_protocol import EVENT_ASSISTANT_REPLY, STATE_REPLYING`
  - [x] Replace inline string `"replying"` in both `assertIn` assertions → `STATE_REPLYING`
  - [x] Replace inline string `"assistant_reply"` in both event filter assertions → `EVENT_ASSISTANT_REPLY`

- [x] Run full test suite and confirm all pass (AC: #1, #2, #3)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — all guard tests pass
  - [x] `uv run pytest tests/` — all tests pass, zero regressions; count should be 154 (153 + 1 new)

## Dev Notes

### Current State — Exact Violations

#### Violation 1: `test_utterance_state_flow.py` uses inline UI strings in assertions

```python
# CURRENT — violates AC #3 ("no inline strings")
self.assertIn(("replying", "Delivering reply", {}), ui.states)
assistant_events = [payload for kind, payload in ui.events if kind == "assistant_reply"]
```

These string literals must be replaced with constants from `contracts.ui_protocol`:
- `"replying"` → `STATE_REPLYING` (value: `"replying"`, an `AppState.REPLYING` StrEnum member)
- `"assistant_reply"` → `EVENT_ASSISTANT_REPLY` (value: `"assistant_reply"`, a `UIEvent.ASSISTANT_REPLY` member)

#### Violation 2: `test_ticks_state_flow.py` uses inline UI strings in assertions

```python
# CURRENT — test_ticks_state_flow.py TickStateFlowTests (two test methods, same pattern each)
self.assertIn(("replying", "Timer completed", {}), ui.states)
assistant_events = [payload for kind, payload in ui.events if kind == "assistant_reply"]
# ...
self.assertIn(("replying", "Pomodoro completed", {}), ui.states)
assistant_events = [payload for kind, payload in ui.events if kind == "assistant_reply"]
```

Same fix needed: replace inline strings with `STATE_REPLYING` and `EVENT_ASSISTANT_REPLY`.

#### Gap: No fast-path pipeline test (FR6 exercise through `process_utterance`)

`test_fast_path.py` tests `maybe_fast_path_response()` in isolation. `test_utterance_state_flow.py` calls `process_utterance()` with `llm_fast_path_enabled=False`. No test exercises the fast-path routing THROUGH `process_utterance()`. Required by AC #3 ("FR6 fast-path routing is verified by existing tests").

### Target Implementation

#### Fix 1: `tests/runtime/test_utterance_state_flow.py`

**Import block — add after the `with patch.dict(...)` import block:**

```python
# src/ is on sys.path via pyproject.toml [tool.pytest.ini_options] pythonpath = ["src"]
from contracts.ui_protocol import EVENT_ASSISTANT_REPLY, STATE_REPLYING
```

**Updated `_AssistantLLMStub` — add call tracking:**

```python
class _AssistantLLMStub:
    def __init__(self, response: dict[str, object]):
        self._response = response
        self.run_call_count = 0

    def run(self, prompt: str, env):
        self.run_call_count += 1
        return dict(self._response)
```

**Updated assertions in `test_process_utterance_uses_state_update_for_replying`:**

```python
# BEFORE
self.assertIn(("replying", "Delivering reply", {}), ui.states)
assistant_events = [payload for kind, payload in ui.events if kind == "assistant_reply"]

# AFTER
self.assertIn((STATE_REPLYING, "Delivering reply", {}), ui.states)
assistant_events = [payload for kind, payload in ui.events if kind == EVENT_ASSISTANT_REPLY]
```

**New test — fast-path pipeline integration (AC #3, FR6):**

```python
def test_process_utterance_fast_path_bypasses_llm(self) -> None:
    ui = _UIServerStub()
    idle_calls: list[str] = []
    llm_stub = _AssistantLLMStub(
        {"assistant_text": "LLM was called unexpectedly", "tool_call": None}
    )

    _fast_path_response = {
        "assistant_text": "Timer gestoppt.",
        "tool_call": {"name": "stop_timer", "arguments": {}},
    }

    with patch(
        "runtime.utterance.maybe_fast_path_response",
        return_value=_fast_path_response,
    ):
        process_utterance(
            object(),
            stt=_STTStub(
                _TranscriptionResultStub(
                    text="Stopp den Timer",
                    language="de",
                    confidence=0.95,
                )
            ),
            assistant_llm=llm_stub,
            speech_service=None,
            logger=logging.getLogger("test"),
            ui=ui,
            build_llm_environment_context=lambda: object(),
            handle_tool_call=lambda tool_call, assistant_text: assistant_text,
            publish_idle_state=lambda: idle_calls.append("idle"),
            llm_fast_path_enabled=True,
        )

    # Fast-path must bypass LLM entirely
    self.assertEqual(
        0,
        llm_stub.run_call_count,
        "LLM must not be called when fast-path handles the request",
    )
    assistant_events = [
        payload for kind, payload in ui.events if kind == EVENT_ASSISTANT_REPLY
    ]
    self.assertEqual(1, len(assistant_events))
    self.assertEqual("Timer gestoppt.", assistant_events[0]["text"])
    self.assertEqual(["idle"], idle_calls)
```

**Why `patch("runtime.utterance.maybe_fast_path_response", return_value=...)` works:**

During module load, `utterance.py` runs:
```python
try:
    from llm.fast_path import maybe_fast_path_response
except Exception:  # pragma: no cover
    maybe_fast_path_response = None
```

Because `llm.fast_path` is NOT in the `sys.modules` stub (only `llm`, `llm.service`, `llm.types` are stubbed), this import fails and `runtime.utterance.maybe_fast_path_response` is bound to `None`. When `process_utterance()` runs `callable(maybe_fast_path_response)`, `None` fails the `callable()` check — fast-path is skipped.

Patching `"runtime.utterance.maybe_fast_path_response"` with a real function replaces the `None` binding in the module namespace, making `callable(maybe_fast_path_response)` return `True` and causing the fast-path to execute.

**Critical**: use `patch("runtime.utterance.maybe_fast_path_response", return_value=_fast_path_response)` — this patches the name in the utterance module's namespace, not the original `llm.fast_path` module.

#### Fix 2: `tests/runtime/test_ticks_state_flow.py`

**File currently starts with `import logging` (missing `from __future__ import annotations`). Insert as the very first line:**

```python
from __future__ import annotations
```

**Then add the constants import (after the stdlib imports block):**

```python
from contracts.ui_protocol import EVENT_ASSISTANT_REPLY, STATE_REPLYING
```

**Updated assertions in `test_timer_completion_publishes_replying_then_idle`:**

```python
# BEFORE
self.assertIn(("replying", "Timer completed", {}), ui.states)
assistant_events = [payload for kind, payload in ui.events if kind == "assistant_reply"]

# AFTER
self.assertIn((STATE_REPLYING, "Timer completed", {}), ui.states)
assistant_events = [payload for kind, payload in ui.events if kind == EVENT_ASSISTANT_REPLY]
```

**Updated assertions in `test_pomodoro_completion_publishes_replying_then_idle`:**

```python
# BEFORE
self.assertIn(("replying", "Pomodoro completed", {}), ui.states)
assistant_events = [payload for kind, payload in ui.events if kind == "assistant_reply"]

# AFTER
self.assertIn((STATE_REPLYING, "Pomodoro completed", {}), ui.states)
assistant_events = [payload for kind, payload in ui.events if kind == EVENT_ASSISTANT_REPLY]
```

### Why `from contracts.ui_protocol import ...` Works Without Path Manipulation

`pyproject.toml` configures:
```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
```

`src/` is on `sys.path` for ALL pytest-run tests. No manual `sys.path.insert()` needed for `contracts.ui_protocol`. This is safe to import directly in any test file.

### Why These Changes Are the Complete Story 1.5 Scope

**Already passing from previous stories:**
- 153/153 tests pass (confirmed via `uv run pytest tests/`) — AC #1 baseline ✅
- All ML dependencies stubbed via `sys.modules` — pvporcupine, faster-whisper, llama-cpp-python, piper-tts never load — AC #2 ✅
- `STTClient`, `LLMClient`, `TTSClient` Protocols in `contracts/pipeline.py` — workers testable without spawning processes — AC #2 ✅
- All 4 guard test classes in `test_contract_guards.py` pass — AC #3 ✅
- `test_utterance_state_flow.py` already tests FR1–5 pipeline — AC #3 (partial) ✅
- `test_fast_path.py` tests FR6 `maybe_fast_path_response()` in isolation — AC #3 (partial) ✅

**Gaps closed by this story:**
- Inline string `"replying"` / `"assistant_reply"` in assertions → replaced with constants — AC #3 ✅
- FR6 exercised THROUGH `process_utterance()` via fast-path pipeline test — AC #3 ✅

### Frozen Value Objects — Already Compliant (No Action Needed)

Story 1.4 audited all 17 high-frequency value objects and confirmed all are `@dataclass(frozen=True, slots=True)`. This story relies on that completed work.

### Guard Tests — Already Compliant (No New Guards Needed for This Story)

The four guard classes are all passing:
- `RuntimeContractGuards` — worker module globals, runtime signature types
- `ContractsConsolidationGuards` — dissolved contracts files, import references
- `LlmModuleBoundaryGuards` — LLM file boundaries, `from __future__` imports
- `DispatchPatternGuards` — match/case in dispatch.py, no if-chain routing

No new guard test is required for Story 1.5. The inline string violations are in TEST files (not guarded source files), and the fix is to update those tests directly.

### Architecture Compliance Checklist

- `from contracts.ui_protocol import STATE_REPLYING, EVENT_ASSISTANT_REPLY` — correct absolute import (no `src.` prefix)
- `patch("runtime.utterance.maybe_fast_path_response", return_value=...)` — patches the module-level name, not the original module
- `_AssistantLLMStub.run_call_count` — lightweight hand-written call tracking (project preference over `MagicMock`)
- All tests remain `unittest.TestCase` subclasses with `if __name__ == "__main__": unittest.main()` entry points
- No new source files created — only existing test files modified
- `uv run pytest tests/runtime/test_contract_guards.py` must still pass after all changes

### Project Structure Notes

- `tests/runtime/test_utterance_state_flow.py` — primary change target (constants + new fast-path test)
- `tests/runtime/test_ticks_state_flow.py` — secondary change target (constants only)
- `src/contracts/ui_protocol.py` — read-only reference; `STATE_REPLYING = AppState.REPLYING` (StrEnum value `"replying"`), `EVENT_ASSISTANT_REPLY = UIEvent.ASSISTANT_REPLY` (StrEnum value `"assistant_reply"`)
- No changes to `src/` production code — this story is test-layer only
- `src/` is on `sys.path` via `[tool.pytest.ini_options] pythonpath = ["src"]` in `pyproject.toml`

### References

- Epics file: `_bmad-output/planning-artifacts/epics.md` — Story 1.5 acceptance criteria (FR27, NFR-T1, NFR-T2)
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "Testability boundary" (all native ML deps stubbable via `sys.modules`), "Test Stub Pattern for Native ML Dependencies" section
- Project context: `_bmad-output/project-context.md` — "Stub Pattern for Heavy Native Dependencies", "Worker Tests — Always Patch `_ProcessWorker`", "Stub Classes — Prefer Lightweight Hand-Written Stubs"
- Story 1.4 dev notes: `_bmad-output/implementation-artifacts/1-4-frozen-value-objects-structural-pattern-matching-dispatch.md` — "Full test suite: 153/153 passed"; confirms the baseline
- Source: `src/contracts/ui_protocol.py` — `STATE_REPLYING = AppState.REPLYING`, `EVENT_ASSISTANT_REPLY = UIEvent.ASSISTANT_REPLY`
- Source: `src/runtime/utterance.py` — `maybe_fast_path_response` binding, fast-path check at line 85
- Test: `tests/runtime/test_utterance_state_flow.py` — primary change target
- Test: `tests/runtime/test_ticks_state_flow.py` — secondary change target
- Implementation sequence note: Step 8 of 8 in Phase 1. Previous story 1-4 is in review. This story closes Phase 1 by verifying the hardware-free test suite guarantee.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Discovered that `unittest.mock.patch.dict` restores `sys.modules` to its full original state on exit, removing any modules imported within the `with` block (including `runtime.utterance`). The story spec's `patch("runtime.utterance.maybe_fast_path_response", ...)` approach would patch a freshly-reimported module instance, not the one bound to `process_utterance.__globals__`. Fixed by using `patch.dict(process_utterance.__globals__, {...})` to target the actual globals dict directly.

### Completion Notes List

- Replaced all inline `"replying"` string literals in `test_utterance_state_flow.py` and `test_ticks_state_flow.py` with `STATE_REPLYING` constant from `contracts.ui_protocol`.
- Replaced all inline `"assistant_reply"` string literals in both files with `EVENT_ASSISTANT_REPLY` constant.
- Added `from __future__ import annotations` as first line of `test_ticks_state_flow.py` (project mandate).
- Added `run_call_count` to `_AssistantLLMStub` to enable fast-path bypass assertion.
- Added `test_process_utterance_fast_path_bypasses_llm` test exercising FR6 through `process_utterance()`. Used `patch.dict(process_utterance.__globals__, ...)` instead of the story spec's `patch("runtime.utterance.maybe_fast_path_response", ...)` — the globals-dict approach is required because `patch.dict` removes `runtime.utterance` from `sys.modules` on exit, meaning the standard patch targets a different module instance.
- Full suite: 154/154 tests pass (153 existing + 1 new). All guard tests pass. Zero regressions.

### File List

- tests/runtime/test_utterance_state_flow.py
- tests/runtime/test_ticks_state_flow.py
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-02-28: Story 1.5 implemented — replaced inline UI string literals with `STATE_REPLYING` and `EVENT_ASSISTANT_REPLY` constants in two test files; added fast-path pipeline integration test; added `from __future__ import annotations` to `test_ticks_state_flow.py`; 154/154 tests pass.

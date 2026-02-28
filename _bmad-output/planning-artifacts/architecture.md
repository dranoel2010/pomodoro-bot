---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-02-28'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/project-context.md
  - docs/index.md
  - docs/architecture.md
  - docs/project-overview.md
  - docs/development-guide.md
  - docs/deployment-guide.md
  - docs/source-tree-analysis.md
workflowType: 'architecture'
project_name: 'pomodoro-bot'
user_name: 'Shrink0r'
date: '2026-02-28'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
39 FRs across 8 capability areas. Core pipeline (FR1–6) is the non-negotiable foundation: sequential wake-word → STT → LLM → TTS with fast-path bypass for deterministic commands (FR6). Phase 2 adds autonomous Pomodoro lifecycle (FR10–14) and UI state reflection (FR15). Tool dispatch (FR16–20) must degrade gracefully when any oracle is unavailable. Developer extensibility (FR25–27) drives the ≤3-file tool-addition constraint that governs contracts consolidation. Performance observability (FR21–24) requires a typed `PipelineMetrics` dataclass emitted per utterance with structured JSON output.

**Non-Functional Requirements:**
- Performance: ≥10 tok/s LLM throughput; ≤25s e2e latency on Pi 5 — hard Phase 1 gate
- Reliability: Worker crash must not kill main process; oracle unavailability must not block voice pipeline; full Pomodoro cycle must run without operator intervention (NFR-R1–3)
- Maintainability: ≤2 files for pure-LLM tool; ≤3 with external dependency; single canonical contracts namespace; composition root as sole instantiation site (NFR-M1–3)
- Testability: Full test suite must pass without hardware, models, or network; each worker's public interface exercisable without real subprocess (NFR-T1–3)
- Deployment: Single self-contained arm64 binary; single TOML config; no required CLI arguments (NFR-D1–2)

**Scale & Complexity:**
- Primary domain: IoT/Embedded ML pipeline daemon (brownfield, pre-production)
- Complexity level: High — multiprocess IPC, constrained ARM hardware, streaming preparation, real-time audio, grammar-constrained LLM output
- Estimated architectural components: ~8 bounded areas — pipeline orchestration, worker process management, contracts/protocols, configuration, tool dispatch, observability, Pomodoro session state, UI/WebSocket

### Technical Constraints & Dependencies

- **ARM64 / Raspberry Pi 5 only** — `compute_type="int8"`, `vad_filter=True`, explicit `n_threads`, `"performance"` CPU governor; all non-negotiable on target hardware
- **Multiprocessing: spawn only** — `fork` context breaks llama.cpp and audio; always use `multiprocessing.get_context("spawn")`
- **Python 3.13+** — `@dataclass(slots=True)`, `X | Y` unions, structural pattern matching in active use; `transformers < 5` ceiling is hard
- **llama-cpp-python GBNF constraint** — LLM output is always grammar-constrained JSON; never free-text; GGUF metadata and grammar API sensitive to version bumps
- **pvporcupine model file binding** — `.ppn`/`.pv` files must match installed pvporcupine version exactly; mismatch causes silent wrong behaviour
- **PyInstaller frozen binary** — single-file arm64 distribution; `getattr(sys, "frozen", False)` guard in config loading path must not be removed
- **Sequential utterance executor** — `ThreadPoolExecutor(max_workers=1)` is a design constraint, not a performance limitation; increasing it would break the single-utterance guarantee
- **All ML workers must compose `_ProcessWorker`** — CPU affinity, logging, restart logic handled by base; never call `psutil` or `os.sched_setaffinity` directly from a worker module

### Cross-Cutting Concerns Identified

1. **Contracts cohesion** — consolidating `src/contracts/`, `runtime/contracts.py`, `oracle/contracts.py` into a single canonical namespace is the primary structural intervention; every other improvement depends on this clarity
2. **IPC envelope typing** — `_RequestEnvelope`/`_ResponseEnvelope` promotion to first-class typed contracts is a streaming prerequisite; without it, stage boundaries are implicit
3. **Configuration ownership** — tri-file config split (loading/schema/parsing) needs explicit boundary rules; the composition root must be the single config entry point
4. **Observability pipeline** — `PipelineMetrics` must be a registerable sink, not just a log line; the web UI rolling latency display in Phase 3 depends on this design
5. **Testability boundary** — all native ML dependencies must be stubbable via `sys.modules` patching without loading real models or spawning real processes
6. **Graceful degradation** — STT, LLM, TTS, and all oracles are optional at runtime; every consumer must null-check before use
7. **Streaming preparation** — Phase 1 must produce Protocol-backed stage boundaries that allow streaming to be implemented as an inter-stage handoff, not an architectural intervention

## Starter Template Evaluation

### Primary Technology Domain

IoT/Embedded ML pipeline daemon — Python, ARM64, local inference.

### Starter Options Considered

This is a brownfield project with full structural freedom but no greenfield scaffolding required. The existing codebase represents the established starter baseline. No starter template migration or scaffolding applies.

### Selected Baseline: Existing Python Daemon Stack

**Rationale:** All technology decisions are already locked and actively in use. Phase 1 work is internal structural refactoring — no dependency changes, no new frameworks, no scaffolding.

**Initialization Command:**

```bash
uv sync  # restore from uv.lock — all dependencies pinned
```

**Architectural Decisions Already Established:**

**Language & Runtime:**
Python 3.13+ required. `from __future__ import annotations` in every module. PEP 563 postponed annotation evaluation in active use. `X | Y` union syntax, `@dataclass(slots=True)`, structural pattern matching — all in active use.

**Process Model:**
`multiprocessing.get_context("spawn")` exclusively. CPU-intensive ML work (STT, LLM, TTS) in dedicated spawned processes with queue-based IPC. `_ProcessWorker` from `workers/core.py` is the sole approved pattern for out-of-process work.

**Package Management:**
`uv` with locked `uv.lock`. All dependency changes via `uv add` — never manual edits to `pyproject.toml`. Hard ceiling: `transformers < 5`. `llama-cpp-python` version changes must be isolated from GGUF model changes.

**Testing Framework:**
`pytest` as runner, `unittest.TestCase` as base. Directory structure mirrors `src/` exactly. All native ML dependencies stubbed via `sys.modules` patching. Meta-tests in `test_contract_guards.py` scan source text to enforce architectural invariants.

**Build & Deployment:**
PyInstaller single-file arm64 binary via `./build.sh`. `getattr(sys, "frozen", False)` guard in `app_config.py` controls config path in frozen mode — must not be removed. Models are not bundled; placed manually at paths declared in `config.toml`.

**Code Organization:**
`src/` on `sys.path` — absolute imports without `src.` prefix. `main.py` is the composition root and sole instantiation site for all ML workers. All external dependency interfaces in `contracts/` (post-Phase-1 consolidation target).

**Development Experience:**
`uv run python src/main.py` from project root. `uv run pytest tests/` for full suite. `APP_CONFIG_FILE` env var overrides default `config.toml` path. Commit style: `feat:`, `fix:`, `refactor:`, `perf:`, `test:`, `chore:` prefixes.

**Note:** No new project initialization story required. Phase 1 begins directly with contracts consolidation.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- Contracts consolidated into `src/contracts/` — no implementation begins until this is resolved; "where does a new interface go?" must have one answer before any story touches interfaces
- IPC envelope types promoted into `src/contracts/` — streaming prerequisite; required before any worker IPC boundary can be independently tested
- Config ownership boundaries made explicit — prevents further ambiguity across the 3 config files during refactoring

**Important Decisions (Shape Architecture):**
- LLM parser module boundary rules — reduces regression risk during parser consolidation
- PipelineMetrics structured logger output — required for Phase 1 performance gate verification; Phase 3 sink deferred

**Deferred Decisions (Post-Phase-1):**
- PipelineMetrics programmatic sink (`metrics_sink: Callable`) — Phase 3 web UI rolling latency display; design hook exists if needed, but not implemented in Phase 1
- Streaming inter-stage handoff protocol — Phase 3 only; enabled by Protocol boundaries established in Phase 1

---

### Data Architecture

**No persistent database.** All runtime state is in-memory:
- `PomodoroTimer` holds session state for the duration of the daemon process
- `RuntimeComponents` dataclass holds all wired collaborators
- Config loaded once at startup from `config.toml`; no runtime config mutation

**PipelineMetrics — Phase 1 Decision: Structured logger only**

`PipelineMetrics` is a `@dataclass(frozen=True, slots=True)` emitted per utterance cycle. Output path: `logger.info(metrics.to_json())` producing machine-readable JSON on the structured log stream. No sink registry, no callback, no event bus in Phase 1.

```python
@dataclass(frozen=True, slots=True)
class PipelineMetrics:
    stt_ms: int
    llm_ms: int
    tts_ms: int
    tokens: int
    tok_per_sec: float
    e2e_ms: int

    def to_json(self) -> str: ...
```

Rationale: Phase 1 gates require mechanical verification via log output. Programmatic sink adds no Phase 1 value and would be speculative infrastructure.

**Phase 3 hook (intentionally deferred):** If a UI latency sink is needed in Phase 3, `metrics_sink: Callable[[PipelineMetrics], None] | None` can be added to `RuntimeComponents` with zero disruption — `PipelineMetrics` is already a typed first-class dataclass.

---

### Authentication & Security

**Security model: local-physical only.** No network authentication surface.

| Asset | Storage | Rule |
|---|---|---|
| `PICO_VOICE_ACCESS_KEY` | `.env`, not committed | Loaded via env var at startup; fails fast if absent |
| Google service account JSON | Absolute path in `.env` | Read at startup; never embedded in binary |
| All other secrets | Env vars only | Never in `config.toml`, never in source |

No credential rotation, no remote management, no network-exposed API in scope for Phase 1 or Phase 2.

---

### API & Communication Patterns

**Three communication channels, all already decided:**

| Channel | Pattern | Direction |
|---|---|---|
| Main ↔ ML Workers | `multiprocessing.Queue` typed messages | Bidirectional; spawn context only |
| Main → Web UI | `websockets` broadcast over ws://localhost:8765 | Outbound only from `RuntimeUIPublisher` |
| LLM output | GBNF grammar-constrained JSON → `StructuredResponse` TypedDict | LLM → parser |

**IPC Envelope Decision: Promote to `src/contracts/`**

`_RequestEnvelope` and `_ResponseEnvelope` move from `_ProcessWorker` internals to `src/contracts/` as first-class `@dataclass(frozen=True, slots=True)` types. This makes stage-boundary types discoverable alongside service Protocol definitions and testable in isolation without spawning processes.

**Fast-path routing:** `llm/fast_path.py` handles deterministic German commands before LLM inference. Returns `StructuredResponse | None`. `None` falls through to full LLM. No fast-path logic in `utterance.py` or `dispatch.py`.

**Error communication:** Worker exceptions (`WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError`) surface in the structured log stream at the same level as `PipelineMetrics` output.

---

### Contracts & Interface Architecture

**Decision: Single canonical namespace — `src/contracts/`**

All Protocol definitions, interface types, and IPC envelope types consolidate into `src/contracts/`. The answer to "where does a new interface go?" is always `src/contracts/`.

**Post-consolidation `src/contracts/` contents:**

| File | Owns |
|---|---|
| `tool_contract.py` | `TOOL_NAME_ORDER`, `TOOLS_WITHOUT_ARGUMENTS`, `TOOL_*` constants, `ToolName` Literal |
| `ui_protocol.py` | `EVENT_*`, `STATE_*` WebSocket constants |
| `pipeline.py` *(new)* | `STTClient`, `LLMClient`, `TTSClient` Protocol definitions (moved from `runtime/contracts.py`) |
| `ipc.py` *(new)* | `_RequestEnvelope`, `_ResponseEnvelope` typed dataclasses (promoted from `_ProcessWorker`) |
| `__init__.py` | `StartupError`; re-exports the full public contracts surface |

`src/runtime/contracts.py` is dissolved. `src/oracle/contracts.py` contents absorbed into `contracts/pipeline.py` or a new `contracts/oracle.py` as appropriate.

---

### LLM Module Boundary Rules

**Decision: Explicit per-file responsibility assignments**

| File | Sole Responsibility | What It Must NOT Do |
|---|---|---|
| `llama_backend.py` | llama.cpp wrapper; GBNF grammar setup; raw inference → raw string | Parse JSON; route commands |
| `parser.py` | Raw string → `StructuredResponse`; JSON normalization + intent fallback | Touch llama.cpp; route commands |
| `fast_path.py` | Deterministic command routing → `StructuredResponse \| None` | Call llama.cpp; parse LLM output |
| `service.py` | Orchestration: fast_path → llama_backend → parser; no parsing logic | Contain any parsing or grammar logic |

These boundaries enable independent unit testing of each file and eliminate the overlapping responsibility that makes parser changes risky.

---

### Infrastructure & Deployment

**All decided and unchanged:**

- **CI/CD:** GitHub Actions on `git push --tags v*`; produces `archive-arm64.tar.gz`
- **Deployment:** Manual — download, extract, replace binary, `sudo systemctl restart pomodoro-bot`
- **Runtime service:** systemd unit; `EnvironmentFile=` for secrets
- **CPU tuning:** `./scripts/pi5_cpu_tuning.sh apply` sets `performance` governor before production use
- **Build reproducibility:** `CMAKE_ARGS=-DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8-a`

---

### Decision Impact Analysis

**Implementation Sequence (enforced by dependency):**

1. `src/contracts/` consolidation — all other Phase 1 work depends on stable interface locations
2. IPC envelope promotion into `src/contracts/ipc.py` — enables worker testability
3. Config boundary enforcement — eliminates ambiguity before config is touched by other stories
4. LLM parser boundary enforcement — reduces regression risk in parser consolidation stories
5. `PipelineMetrics` typed dataclass + structured log emission — enables performance gate verification
6. `@dataclass(frozen=True, slots=True)` on all high-frequency value objects — once contracts stable
7. Structural pattern matching in dispatch — depends on stable `ToolName` type from contracts
8. Performance gate measurement and tuning — final Phase 1 gate check

**Cross-Component Dependencies:**

- `ToolName` Literal type (in `contracts/tool_contract.py`) feeds LLM GBNF grammar generation, dispatch routing, and fast-path matching — contracts must stabilise before any of these are touched
- `PipelineMetrics` lives in `llm/types.py` — it is a result type, not a contract; close to the utterance pipeline that emits it
- `RuntimeComponents` is the composition seam — all new injectable collaborators go here, never as `RuntimeEngine.__init__` parameters

## Implementation Patterns & Consistency Rules

### Critical Conflict Points Identified

8 areas where AI agents will make inconsistent choices without explicit rules:
1. Where new Protocol/interface definitions belong
2. How to add a new ML worker process
3. How to add a new tool call
4. How errors are wrapped at startup vs runtime
5. What language user-facing strings use
6. How to write tests for modules with native ML dependencies
7. How to handle optional runtime components (null checks)
8. Import style and union type syntax

---

### Naming Patterns

**Module / File Naming:**
- All `src/` modules: `snake_case.py` — never PascalCase files
- Never shadow a stdlib or third-party package name (e.g. no `logging.py`, `queue.py`, `json.py`)
- Worker modules: named after the ML service they wrap (`llm.py`, `stt.py`, `tts.py`)
- New contracts files: noun-based, describes the domain boundary (`pipeline.py`, `ipc.py`, `oracle.py`)

**Code Naming:**

| Item | Convention | Example |
|---|---|---|
| Modules / files | `snake_case.py` | `fast_path.py` |
| Classes | `PascalCase` | `LLMWorker` |
| Functions, methods, variables | `snake_case` | `process_utterance` |
| Constants | `UPPER_SNAKE_CASE` | `TOOL_NAME_ORDER` |
| Private module-level helpers | `_leading_underscore` | `_build_llm_stub_modules` |
| Private class attributes | `self._leading_underscore` | `self._process` |

**Language Rule — Non-Negotiable:**
- All Python identifiers, comments, docstrings: **English**
- All user-facing strings (TTS output, spoken messages, status announcements): **German**
- `runtime/tools/messages.py` default messages: German
- `EnvironmentContext.to_prompt_placeholders()` produces German datetime strings

---

### Structural Patterns

**Where New Things Go — Decision Table:**

| New Item | Correct Location | Wrong Location |
|---|---|---|
| New Protocol / interface | `src/contracts/pipeline.py` or `contracts/oracle.py` | `runtime/contracts.py` ❌ anywhere else ❌ |
| New IPC envelope type | `src/contracts/ipc.py` | Inside `_ProcessWorker` ❌ |
| New WebSocket event/state constant | `src/contracts/ui_protocol.py` | Inline string ❌ |
| New tool name constant | `src/contracts/tool_contract.py` | Any other file ❌ |
| New env var name constant | `src/shared/env_keys.py` | `os.getenv("HARDCODED")` ❌ |
| New injectable collaborator | `RuntimeComponents` dataclass + `_build_runtime_components()` | `RuntimeEngine.__init__` params ❌ |
| New deterministic command pattern | `llm/fast_path.py` | `utterance.py` ❌ `dispatch.py` ❌ |
| New timer-type feature | Explicit new tool set + startup sync | Unassigned to a channel ❌ |

**Test Structure:**
- `tests/` mirrors `src/` exactly: `tests/runtime/` → `src/runtime/`
- Every test subdirectory has `__init__.py`
- Test files named `test_*.py`
- No test logic in `src/`

---

### Format Patterns

**Dataclass Style — Two Variants, No Others:**

```python
# Immutable value objects (IPC envelopes, metrics, payloads):
@dataclass(frozen=True, slots=True)
class LLMPayload:
    user_prompt: str
    env: EnvironmentContext | None = None

# Runtime containers (components, mutable state holders):
@dataclass(slots=True)
class RuntimeComponents:
    ...

# NEVER: plain @dataclass without slots on high-frequency types
# NEVER: TypedDict for value objects that are constructed internally
```

**`StructuredResponse` — LLM Output Contract:**
```python
class StructuredResponse(TypedDict):
    assistant_text: str          # may be empty string — always check before TTS
    tool_call: ToolCall | None   # always access via typed keys only
```
No extra fields assumed. `assistant_text` may be empty — pipeline skips TTS if falsy.

**Structured Log Format (PipelineMetrics):**
```
{"event": "pipeline_metrics", "stt_ms": N, "llm_ms": N, "tts_ms": N,
 "tokens": N, "tok_per_sec": F, "e2e_ms": N}
```
Emitted synchronously per utterance. No batch aggregation.

**Runtime Signature Rule** (enforced by `test_contract_guards.py`):
- `dict[str, object]` is FORBIDDEN in `utterance.py`, `dispatch.py`, `calendar.py`, `ui.py`
- Use `ToolCall`, `StructuredResponse`, `TypedDict` instead

---

### Communication Patterns

**IPC — Queue Messages:**
- All inter-process messages are typed `@dataclass(frozen=True, slots=True)` — never raw dicts
- Only `QueueEventPublisher` writes to the event queue — never `event_queue.put()` directly
- Worker `call()` returns typed result or raises `WorkerCallTimeoutError | WorkerCrashError | WorkerTaskError`
- Each exception type has different recovery semantics — catch separately

**WebSocket UI Events:**
```python
# CORRECT
from contracts.ui_protocol import EVENT_ERROR, STATE_IDLE
ui_publisher.publish_state(STATE_IDLE)

# WRONG — never
ui_publisher.publish_state("idle")
```

**Tool Dispatch:**
```python
# CORRECT — structural pattern matching
match tool_call.name:
    case TOOL_START_TIMER:
        return await handle_start_timer(context)
    case TOOL_TELL_JOKE:
        return await handle_tell_joke(context)

# WRONG — if/elif chains
if tool_call.name == "start_timer": ...
elif tool_call.name == "tell_joke": ...
```

---

### Process Patterns

**Adding a New Tool Call — Full Checklist (5 steps):**
1. Add constant + append to `TOOL_NAME_ORDER` in `contracts/tool_contract.py`
2. If no arguments: add to `TOOLS_WITHOUT_ARGUMENTS` — missing this causes malformed LLM grammar
3. If arguments: do NOT add to `TOOLS_WITHOUT_ARGUMENTS`
4. Add `case` arm + handler in `tools/dispatch.py`
5. Add to appropriate tool set (`TIMER_TOOL_NAMES`, `POMODORO_TOOL_NAMES`, `CALENDAR_TOOL_NAMES`) if applicable

Minimal pure-LLM tool: 2 files changed (`tool_contract.py` + `dispatch.py`). Tool with external dependency: 3 files max.

**Adding a New ML Worker Process — Full Checklist (5 steps):**
1. `_SomeRuntime` class with `handle(payload) -> result` (in-process logic)
2. Typed payload: `@dataclass(frozen=True, slots=True)`
3. Public worker class composing `_ProcessWorker` from `workers/core.py`
4. `create_*_worker()` factory returning `Worker | None` — raises `StartupError` on failure
5. Wire into `RuntimeComponents` + `_build_runtime_components()` in `main.py`

**Startup Error Wrapping:**
```python
from contracts import StartupError

try:
    worker = SomeWorker(config)
except SomeSpecificError as exc:
    raise StartupError(f"Descriptive message: {exc}") from exc
# Never propagate raw exceptions from startup/init paths
```

**Optional Component Null Check Pattern:**
```python
# Factory returns None when component is disabled
worker = create_llm_worker(config)  # LLMWorker | None
if worker is None:
    logger.warning("LLM disabled; skipping spoken response.")
    return

# Oracle is only constructed when LLM is enabled
if assistant_llm is not None:
    oracle = create_oracle_service(config)
```

**Import Pattern — Every Module:**
```python
from __future__ import annotations  # ALWAYS first line, no exceptions

# Order: stdlib → third-party → local absolute → local relative → TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llm.types import EnvironmentContext  # circular-safe

# Union types: X | Y always — never Optional[X] or Union[X, Y]
def run(self, env: EnvironmentContext | None = None) -> StructuredResponse: ...
```

**Test Stub Pattern for Native ML Dependencies:**
```python
# Stub before import — never let real llama-cpp-python/faster-whisper/piper load in tests
with patch.dict(sys.modules, {**_build_llm_stub_modules()}):
    from runtime.utterance import process_utterance
```

---

### Enforcement Guidelines

**All AI Agents MUST:**
- Check `src/contracts/` before placing any new Protocol, interface, or IPC type
- Run `uv run pytest tests/runtime/test_contract_guards.py` after any structural change
- Verify `TOOLS_WITHOUT_ARGUMENTS` membership whenever adding a new tool
- Use `_ProcessWorker` — never call `multiprocessing.Process(...)` directly
- Use `spawn` context — never `fork`
- Never hardcode tool names, UI event strings, or env var names as literals

**Pattern Enforcement:**
- `tests/runtime/test_contract_guards.py` scans raw source text for structural violations
- New modules under guarded paths must be checked against guard rules explicitly
- The guard tests are not optional — a passing test suite is a Phase 1 AND gate

## Project Structure & Boundaries

### Complete Project Directory Structure (Target: Post-Phase-1)

```
pomodoro-bot/
├── .env                          ← Secrets only (PICO_VOICE_ACCESS_KEY, HF_TOKEN, etc.)
├── .env.dist                     ← Template; no real values committed
├── .github/
│   └── workflows/
│       └── release.yml           ← CI: builds arm64 binary on git push --tags v*
├── build.sh                      ← PyInstaller invocation
├── pyproject.toml                ← uv-managed dependencies; transformers<5 ceiling enforced here
├── uv.lock                       ← Pinned; never edit manually
├── config.toml                   ← All runtime config; no secrets
├── dist/
│   └── config.toml               ← Reference config shipped with binary
├── models/
│   ├── sst/                      ← hey-pomo.ppn + porcupine_params_de.pv (not in git)
│   ├── tts/thorsten-piper/       ← ONNX TTS model (not in git)
│   └── llm/qwen/                 ← GGUF LLM model (not in git)
├── scripts/
│   ├── pi5_cpu_tuning.sh         ← Sets 'performance' governor
│   └── pi5_build_optimized_inference.sh  ← On-device llama.cpp rebuild
├── docs/                         ← Project documentation
├── web_ui/                       ← Static HTML/JS/CSS themes for browser UI
├── training/                     ← Fine-tuning dataset generation scripts
├── src/
│   ├── main.py                   ← Composition root; sole instantiation site for all workers
│   ├── app_config.py             ← I/O only: reads file + env vars, calls parser, returns AppConfig
│   ├── app_config_schema.py      ← Pure dataclasses: AppConfig, SecretConfig, *Settings
│   ├── app_config_parser.py      ← TOML bytes → typed config; no I/O
│   │
│   ├── contracts/                ← ★ SINGLE CANONICAL NAMESPACE for all interfaces (Phase 1 target)
│   │   ├── __init__.py           ← StartupError; re-exports full public contracts surface
│   │   ├── tool_contract.py      ← TOOL_NAME_ORDER, TOOLS_WITHOUT_ARGUMENTS, TOOL_* constants
│   │   ├── ui_protocol.py        ← EVENT_*, STATE_* WebSocket constants
│   │   ├── pipeline.py           ← ★ NEW: STTClient, LLMClient, TTSClient Protocols
│   │   │                           (moved from runtime/contracts.py — file dissolved)
│   │   └── ipc.py                ← ★ NEW: _RequestEnvelope, _ResponseEnvelope typed dataclasses
│   │                               (promoted from _ProcessWorker internals)
│   │
│   ├── llm/
│   │   ├── types.py              ← StructuredResponse, EnvironmentContext, ToolCall, ToolName,
│   │   │                           PipelineMetrics (★ NEW Phase 1)
│   │   ├── service.py            ← Orchestration only: fast_path → llama_backend → parser
│   │   ├── llama_backend.py      ← llama.cpp wrapper; GBNF grammar; raw inference → raw string
│   │   ├── fast_path.py          ← Deterministic command router; returns StructuredResponse | None
│   │   ├── parser.py             ← JSON normalization + intent fallback → StructuredResponse
│   │   ├── model_store.py        ← GGUF download/validation from HuggingFace
│   │   ├── config.py             ← LLMConfig validated settings
│   │   └── factory.py            ← create_llm_config()
│   │
│   ├── stt/
│   │   ├── events.py             ← Utterance, QueueEventPublisher, event dataclasses
│   │   ├── service.py            ← WakeWordService
│   │   ├── stt.py                ← TranscriptionResult, STTError
│   │   └── factory.py
│   │
│   ├── tts/
│   │   ├── engine.py             ← TTSError
│   │   ├── service.py
│   │   ├── output.py
│   │   └── factory.py
│   │
│   ├── oracle/
│   │   ├── service.py            ← OracleContextService (env sensor + calendar data)
│   │   ├── providers.py
│   │   ├── factory.py
│   │   ├── calendar/
│   │   │   └── google_calendar.py
│   │   └── sensor/
│   │       ├── ens160_sensor.py
│   │       └── temt6000_sensor.py
│   │
│   ├── pomodoro/
│   │   ├── constants.py          ← ACTION_*, REASON_* string constants
│   │   ├── service.py            ← PomodoroTimer (Phase 2: autonomous transitions)
│   │   └── tool_mapping.py
│   │
│   ├── server/
│   │   ├── service.py            ← UIServer (WebSocket; ws://localhost:8765)
│   │   ├── ui_server.py
│   │   └── factory.py
│   │
│   ├── shared/
│   │   ├── env_keys.py           ← ENV_* constants for all environment variable names
│   │   ├── defaults.py
│   │   └── spoken_time.py
│   │
│   ├── runtime/
│   │   ├── __init__.py           ← Exports RuntimeEngine only
│   │   ├── engine.py             ← RuntimeEngine + RuntimeComponents dataclass
│   │   ├── utterance.py          ← process_utterance() — STT→LLM→tool→TTS pipeline
│   │   ├── ticks.py              ← Pomodoro/timer tick handlers
│   │   ├── ui.py                 ← RuntimeUIPublisher facade
│   │   ├── tools/
│   │   │   ├── dispatch.py       ← RuntimeToolDispatcher (match statement)
│   │   │   ├── messages.py       ← German status/fallback messages
│   │   │   └── calendar.py       ← Calendar argument parsing + handlers
│   │   └── workers/
│   │       ├── core.py           ← _ProcessWorker, WorkerError hierarchy
│   │       ├── llm.py            ← LLMWorker, create_llm_worker()
│   │       ├── stt.py            ← create_stt_worker()
│   │       └── tts.py            ← create_tts_worker()
│   │
│   └── debug/
│       └── audio_diagnostic.py   ← VAD visualiser + ALSA device selector
│
└── tests/                        ← Mirrors src/ exactly
    ├── runtime/
    │   ├── test_contract_guards.py  ← Meta-tests: scan source text for structural violations
    │   ├── test_engine.py
    │   ├── test_utterance.py
    │   └── workers/
    ├── llm/
    ├── stt/
    ├── tts/
    ├── oracle/
    ├── server/
    ├── pomodoro/
    └── config/
```

### Architectural Boundaries

**Process Boundaries (Spawn-Isolated):**

```
[main process]
  ├── RuntimeEngine (event loop + ThreadPoolExecutor(max_workers=1))
  ├── UIServer (WebSocket broadcast)
  ├── OracleContextService (calendar + sensor I/O)
  ├── PomodoroTimer (in-memory state)
  └── QueueEventPublisher → event queue
         ↑
  [WakeWordService thread] → publishes UtteranceCapturedEvent
         ↓
  [STT worker process]  — core 0
  [LLM worker process]  — cores 1–2
  [TTS worker process]  — core 3
```

**IPC Boundary (`contracts/ipc.py`):**
All cross-process messages flow through typed `_RequestEnvelope` / `_ResponseEnvelope` dataclasses. No raw dicts, no arbitrary pickling.

**Contracts Boundary (`contracts/`):**
Everything that crosses a module boundary as an injectable dependency is a `Protocol` defined in `contracts/`. No `ABC`. No unnamed duck-typing.

**Config Boundary:**
- `app_config_schema.py` — zero I/O; pure types
- `app_config_parser.py` — zero I/O; TOML bytes → types
- `app_config.py` — all I/O; single public entry point `_load_runtime_config()`
- Secrets: env vars only; never in `config.toml`

**WebSocket Boundary:**
All outbound UI state flows through `RuntimeUIPublisher` → `UIServer.broadcast()`. No module calls `UIServer` directly. All event/state strings from `contracts/ui_protocol.py`.

### Requirements → Structure Mapping

| FR Group | Primary Files | Phase |
|---|---|---|
| FR1–5: Voice pipeline | `runtime/utterance.py`, `runtime/engine.py`, `runtime/workers/` | Existing |
| FR6: Fast-path | `llm/fast_path.py` | Existing |
| FR7–9: Pomodoro voice commands | `contracts/tool_contract.py`, `runtime/tools/dispatch.py` | Existing |
| FR10–15: Autonomous Pomodoro cycle | `pomodoro/service.py`, `runtime/ticks.py` | Phase 2 |
| FR16–20: Tool dispatch + degradation | `runtime/tools/dispatch.py`, `contracts/tool_contract.py` | Existing |
| FR21–24: PipelineMetrics + observability | `llm/types.py` (PipelineMetrics), `runtime/utterance.py` | Phase 1 |
| FR25–27: Developer extensibility | `contracts/`, `tests/runtime/test_contract_guards.py` | Phase 1 |
| FR28–29: CPU config + config override | `app_config_schema.py`, `shared/env_keys.py` | Existing |
| FR30–32: Oracle/sensor context | `oracle/service.py`, `oracle/sensor/`, `oracle/calendar/` | Existing |
| FR33–35: Web UI | `server/service.py`, `web_ui/`, `contracts/ui_protocol.py` | Existing |
| FR36–39: Ops / diagnostics | `app_config.py`, `dist/config.toml`, `scripts/`, `src/debug/` | Existing |

### Data Flow

```
[Wake word detected]
        ↓
WakeWordService → QueueEventPublisher → RuntimeEngine event queue
        ↓
ThreadPoolExecutor(max_workers=1) → process_utterance()
  ├── STTClient.transcribe()       [spawned process, core 0]
  ├── fast_path check              [in-process, no LLM]
  ├── OracleContextService.get()   [optional; calendar + sensors]
  ├── LLMClient.run()              [spawned process, cores 1–2]
  ├── RuntimeToolDispatcher        [in-process; match statement]
  ├── TTSClient.speak()            [spawned process, core 3]
  └── PipelineMetrics.to_json()    [structured log emission]
        ↓
RuntimeUIPublisher → UIServer → WebSocket broadcast → browser
```

### Development Workflow Integration

**Development (macOS):**
```bash
uv sync
source .env
uv run python src/main.py
uv run pytest tests/
```

**Target Hardware:**
```bash
source .env && ./main   # frozen binary; config.toml beside executable
sudo systemctl restart pomodoro-bot  # post-update
```

**Release trigger:**
```bash
git push --tags v1.0.0  # GitHub Actions builds archive-arm64.tar.gz
```

## Architecture Validation Results

### Coherence Validation ✅

All technology choices are mutually compatible and internally consistent. No conflicting version decisions. Patterns align with technology constraints (spawn+llama.cpp, frozen dataclasses+Pi 5 performance, Protocol+testability). Structure enforced by existing guard tests. No coherence issues found.

### Requirements Coverage Validation ✅

**Functional Requirements:** All 39 FRs covered across 8 groups. FR10–15 (autonomous Pomodoro) are Phase 2 — architecturally prepared in `pomodoro/service.py` + `runtime/ticks.py`.

**Non-Functional Requirements:** All 12 NFRs addressed. Performance gates enforced by Phase 1 AND condition. Testability achieved through IPC envelope promotion + `sys.modules` stub pattern. Deployment via PyInstaller arm64 binary.

### Implementation Readiness Validation ✅

Decisions are complete with rationale. Patterns include concrete code examples and anti-patterns. Project structure is specific to this codebase — no generic placeholders. All 8 identified agent conflict points have explicit resolution rules. Guard tests provide mechanical enforcement.

### Gap Analysis Results

**Important Gaps:**
- `contracts/oracle.py` scope: examine `src/oracle/contracts.py` contents during contracts consolidation story; absorb into `pipeline.py` or create `oracle.py` accordingly
- Guard coverage extension: update `test_contract_guards.py` when new runtime modules are added in Phase 2

**Deferred (Nice-to-Have):**
- Benchmark result JSON schema for automated Phase 1 gate verification

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Project context thoroughly analyzed (39 FRs, 12 NFRs, 47 project-context rules)
- [x] Scale and complexity assessed (High: multiprocess IPC, ARM64, streaming preparation)
- [x] Technical constraints identified (Pi 5 hardware, spawn-only, transformers<5, GBNF)
- [x] Cross-cutting concerns mapped (7 concerns documented)

**✅ Architectural Decisions**
- [x] Contracts consolidation: single `src/contracts/` namespace
- [x] IPC envelopes promoted to `contracts/ipc.py`
- [x] Config ownership boundaries: schema / parser / I/O separation
- [x] PipelineMetrics: structured logger only in Phase 1
- [x] LLM module boundary rules: 4 files, explicit responsibility assignments
- [x] Implementation sequence: 8-step ordered dependency chain

**✅ Implementation Patterns**
- [x] 8 critical agent conflict points identified and resolved
- [x] Naming conventions: full table with examples
- [x] Where-new-things-go decision table
- [x] Dataclass style: two variants documented with examples
- [x] Tool addition checklist: 5 steps
- [x] Worker addition checklist: 5 steps
- [x] Startup error wrapping pattern
- [x] Optional component null-check pattern
- [x] Import pattern and union type syntax
- [x] Test stub pattern for native ML dependencies

**✅ Project Structure**
- [x] Complete annotated directory tree (post-Phase-1 target)
- [x] Process boundaries diagram
- [x] Data flow diagram
- [x] FR → module mapping table (39 FRs)
- [x] Architectural boundaries defined (IPC, contracts, config, WebSocket)

### Architecture Readiness Assessment

**Overall Status: READY FOR IMPLEMENTATION**

**Confidence Level: High** — brownfield project with full structural freedom, no migration costs, comprehensive existing documentation, and a clear measurable Phase 1 gate.

**Key Strengths:**
1. Phase gate is explicit and mechanical — 3 AND conditions with numerical thresholds
2. Contracts consolidation unblocks all other Phase 1 stories — correct sequencing
3. Streaming north star is prepared without over-engineering — Protocol boundaries are the only Phase 1 prerequisite for Phase 3
4. Guard tests provide automated enforcement — architecture violations are caught, not just documented
5. Test isolation pattern is fully specified — hardware-free test suite is achievable from day one of Phase 1

**Areas for Future Enhancement:**
1. `PipelineMetrics` sink registry — Phase 3 web UI rolling latency display
2. `contracts/oracle.py` — oracle-specific Protocols if oracle scope grows
3. `test_contract_guards.py` coverage expansion — as Phase 2 adds new runtime modules
4. Benchmark JSON schema — formalise automated Phase 1 gate check

### Implementation Handoff

**AI Agent Guidelines:**
- Read `src/contracts/` before placing any new Protocol, interface, or IPC type
- Follow the 5-step tool addition checklist — `TOOLS_WITHOUT_ARGUMENTS` omission causes silent LLM grammar failure
- Run `uv run pytest tests/runtime/test_contract_guards.py` after any structural change
- All user-facing strings are German; all identifiers are English — without exception
- `RuntimeComponents` is the composition seam — new collaborators go there, not in `RuntimeEngine.__init__`

**First Implementation Story:**
Contracts consolidation — merge `runtime/contracts.py` + `oracle/contracts.py` into `src/contracts/pipeline.py`; promote IPC envelope types to `src/contracts/ipc.py`; dissolve source files; update all import sites; run full test suite. All subsequent Phase 1 stories depend on this being stable.

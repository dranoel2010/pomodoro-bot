---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/architecture.md'
---

# pomodoro-bot - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for pomodoro-bot, decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

**Voice Interaction Pipeline**

- FR1: The system can detect a predefined wake word from ambient audio to initiate an interaction cycle
- FR2: The system can transcribe a spoken German-language utterance to text
- FR3: The system can generate a contextually appropriate text response given a transcribed utterance
- FR4: The system can synthesise a text response into spoken German-language audio
- FR5: The system can execute the complete interaction cycle (wake-word → STT → LLM → TTS) sequentially without user intervention between stages
- FR6: The system can route deterministic utterances directly to a handler without LLM inference

**Pomodoro Session Management**

- FR7: The user can start a Pomodoro work session via voice command
- FR8: The user can stop an active Pomodoro session via voice command
- FR9: The user can query the current session status and elapsed time via voice command
- FR10: The system can autonomously transition from a work phase to a short break after the configured work duration expires
- FR11: The system can autonomously transition from a short break back to a work phase after the configured break duration expires
- FR12: The system can autonomously trigger a long break after four consecutive work sessions complete
- FR13: The system can autonomously reset the Pomodoro cycle to its initial state after a long break completes
- FR14: The system can announce each phase transition with a spoken notification without a user command
- FR15: The web UI can reflect the current Pomodoro phase and session count in real time

**Tool Dispatch & Execution**

- FR16: The system can route a recognised intent to the appropriate tool handler based on the tool name
- FR17: The system can execute a tool that produces a response using only LLM inference (no external dependency)
- FR18: The system can execute a tool that queries the optional calendar oracle for context
- FR19: The system can execute a tool that queries optional I²C sensor data for context
- FR20: The system can operate correctly when optional oracle integrations are unavailable or disabled

**Performance Observability**

- FR21: The system can emit per-utterance structured metrics including per-stage latency (STT, LLM, TTS) and LLM token throughput
- FR22: The system can emit per-utterance metrics as structured log output in a machine-readable format
- FR23: The system can surface worker errors in the same structured output stream as pipeline metrics
- FR24: A developer can run a throughput benchmark across LLM model variants and thread configurations on target hardware

**Developer Extensibility**

- FR25: A developer can register a new tool by modifying the tool contract registry and the dispatch handler
- FR26: A developer can locate all external dependency interface definitions in a single canonical namespace
- FR27: A developer can run the complete test suite without physical audio hardware, wake-word models, or ML models
- FR28: A developer can configure CPU core assignments for each ML worker independently via config file
- FR29: A developer can override the default config file path at runtime via environment variable

**Calendar & Sensor Context (Oracle)**

- FR30: The system can optionally retrieve upcoming calendar events to enrich the LLM context for a given utterance
- FR31: The system can optionally retrieve air quality sensor readings to enrich the LLM context
- FR32: The system can optionally retrieve ambient light level readings to enrich the LLM context

**Web UI & Visibility**

- FR33: The user can observe the current assistant state via a browser-based interface
- FR34: The web UI can be served over WebSocket to any browser on the local network
- FR35: The user can select between available web UI themes

**System Configuration & Operation**

- FR36: An operator can configure all required pipeline parameters (model paths, wake-word files, CPU assignments) in a single configuration file
- FR37: An operator can run the assistant as a persistent background system service
- FR38: An operator can diagnose audio input quality and VAD sensitivity using an included diagnostic utility
- FR39: An operator can apply CPU performance governor settings for optimal inference throughput using an included script

### NonFunctional Requirements

**Performance**

- NFR-P1: LLM throughput must be ≥ 10 tokens/second on Raspberry Pi 5 under representative conversational load, measured using the included model sweep benchmark
- NFR-P2: End-to-end latency (wake-word detection → first spoken word of response) must be ≤ 25 seconds, measured across a minimum of 3 representative utterances
- NFR-P3: `PipelineMetrics` must be emitted synchronously with each completed utterance cycle — no buffering or batch aggregation

**Reliability**

- NFR-R1: A crash or exception in any ML worker subprocess (STT, LLM, TTS) must not terminate the main process; the failure must be logged in the structured output stream and the system must remain in a recoverable state
- NFR-R2: Unavailability or misconfiguration of any optional oracle integration (calendar, air quality, ambient light) must not prevent the voice pipeline from completing an interaction
- NFR-R3: The system must complete the full Pomodoro cycle autonomously (all four work sessions, short breaks, long break, cycle reset) without requiring operator intervention or manual commands after session start

**Maintainability**

- NFR-M1: Adding a new tool call that requires no external oracle dependency must require changes to at most 2 source files; a tool with an external dependency must require at most 3 source files
- NFR-M2: All external dependency interface definitions must reside in a single canonical namespace such that a developer unfamiliar with the codebase can locate the correct interface definition without tracing import chains
- NFR-M3: The composition root (`main.py`) must be the sole location where ML worker instances are constructed and wired together; no hidden instantiation may occur within subordinate modules

**Testability**

- NFR-T1: The complete test suite must pass without physical audio hardware, ML model files, wake-word model files, or network access
- NFR-T2: Each ML worker's public interface must be exercisable in tests without spawning a real subprocess or loading a real model
- NFR-T3: `PipelineMetrics` emission must be verifiable via unit test without executing an end-to-end utterance cycle

**Deployment**

- NFR-D1: The system must be distributable as a single self-contained arm64 binary that includes all Python dependencies and does not require a pre-installed Python runtime on the target device
- NFR-D2: All required runtime configuration (model paths, wake-word files, CPU assignments) must be fully expressible in a single TOML configuration file with no required command-line arguments at startup

### Additional Requirements

**From Architecture — Structural (Phase 1 blockers):**

- Contracts consolidation: `src/runtime/contracts.py` and `src/oracle/contracts.py` must be dissolved into a single `src/contracts/` canonical namespace; all Protocol and interface definitions live there exclusively
- IPC envelope types (`_RequestEnvelope`, `_ResponseEnvelope`) must be promoted to `src/contracts/ipc.py` as first-class `@dataclass(frozen=True, slots=True)` typed dataclasses — currently buried in `_ProcessWorker` internals
- Config boundary rules must be made explicit: `app_config_schema.py` (pure types, zero I/O), `app_config_parser.py` (TOML bytes → typed config, zero I/O), `app_config.py` (all I/O, single entry point)
- LLM module boundary rules enforced: `llama_backend.py` (raw inference only), `parser.py` (JSON normalisation only), `fast_path.py` (deterministic routing only), `service.py` (orchestration only — no parsing logic)
- Misleading module names corrected (e.g. `runtime/tools/messages.py`, `src/stt/stt.py` scope must match name)

**From Architecture — Implementation Patterns:**

- `@dataclass(frozen=True, slots=True)` required on all high-frequency value objects (IPC envelopes, metrics, payloads)
- Structural pattern matching (`match`/`case`) required in tool dispatch — `if/elif` chains are forbidden
- `from __future__ import annotations` must be the first line of every Python module — no exceptions
- `multiprocessing.get_context("spawn")` exclusively — `fork` context is forbidden
- CPU core assignment enforced via `os.sched_setaffinity` at worker startup: STT→core 0, LLM→cores 1–2, TTS→core 3
- `ThreadPoolExecutor(max_workers=1)` is a design constraint — must not be changed
- `RuntimeComponents` dataclass is the sole composition seam — new collaborators wired there, never in `RuntimeEngine.__init__`
- All user-facing strings (TTS, spoken announcements) must be German; all identifiers, comments, docstrings must be English

**From Architecture — Observability:**

- `PipelineMetrics` must be a `@dataclass(frozen=True, slots=True)` with fields: `stt_ms`, `llm_ms`, `tts_ms`, `tokens`, `tok_per_sec`, `e2e_ms`; emitted via `logger.info(metrics.to_json())` in machine-readable JSON format
- Structured log format: `{"event": "pipeline_metrics", "stt_ms": N, "llm_ms": N, "tts_ms": N, "tokens": N, "tok_per_sec": F, "e2e_ms": N}`
- Worker error exceptions (`WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError`) must surface in the structured log at the same level as `PipelineMetrics`

**From Architecture — Enforcement:**

- Guard tests in `tests/runtime/test_contract_guards.py` scan source text for structural violations; must remain green after every structural change
- Phase 1 performance gate is a hard AND condition: ≥10 tok/s LLM throughput AND ≤25s E2E latency — both must be true before Phase 2 begins
- Phase 1 implementation sequence (enforced by dependency): contracts consolidation → IPC envelope promotion → config boundary → LLM parser boundary → PipelineMetrics → frozen dataclasses → pattern matching dispatch → performance gate verification

**No UX Design document:** No browser-based UI design document exists. Web UI requirements are limited to WebSocket push behaviour (FR33–35) captured in the PRD.

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 1 | Wake-word detection — maintained through structural refactor |
| FR2 | Epic 1 | German STT transcription — maintained through refactor |
| FR3 | Epic 1 | LLM response generation — maintained through refactor |
| FR4 | Epic 1 | German TTS synthesis — maintained through refactor |
| FR5 | Epic 1 | Sequential pipeline execution — maintained, verified |
| FR6 | Epic 1 | Deterministic fast-path routing — remains in `fast_path.py` |
| FR7 | Epic 3 | Start Pomodoro via voice command |
| FR8 | Epic 3 | Stop Pomodoro via voice command |
| FR9 | Epic 3 | Query session status via voice |
| FR10 | Epic 3 | Autonomous work→break transition |
| FR11 | Epic 3 | Autonomous break→work transition |
| FR12 | Epic 3 | Long break after 4 sessions |
| FR13 | Epic 3 | Cycle reset after long break |
| FR14 | Epic 3 | Spoken transition announcements |
| FR15 | Epic 3 | Web UI reflects current phase + session count |
| FR16 | Epic 1 | Tool dispatch refactored to structural pattern matching |
| FR17 | Epic 4 | Pure-LLM tool (`tell_joke`) — 2-file proof of extensibility |
| FR18 | Epic 4 | Calendar oracle tool |
| FR19 | Epic 4 | I²C sensor oracle tool |
| FR20 | Epic 4 | Graceful oracle degradation |
| FR21 | Epic 2 | Per-utterance structured metrics (stt/llm/tts/tok_per_sec/e2e) |
| FR22 | Epic 2 | Machine-readable JSON log output |
| FR23 | Epic 2 | Worker errors in same structured stream |
| FR24 | Epic 2 | Model sweep benchmark tooling |
| FR25 | Epic 1 | New tool registration in ≤2 files |
| FR26 | Epic 1 | Single canonical interface namespace |
| FR27 | Epic 1 | Hardware-free test suite |
| FR28 | Epic 1 | CPU core assignment per worker via config |
| FR29 | Epic 1 | Config path override via env var |
| FR30 | Epic 4 | Calendar events enrich LLM context |
| FR31 | Epic 4 | Air quality sensor in LLM context |
| FR32 | Epic 4 | Ambient light sensor in LLM context |
| FR33 | Epic 1 | Browser-based state view — maintained through refactor |
| FR34 | Epic 1 | WebSocket serve to LAN browsers — maintained |
| FR35 | Epic 1 | UI theme selection — maintained |
| FR36 | Epic 1 | Single config file for all pipeline parameters |
| FR37 | Epic 2 | systemd persistent background service |
| FR38 | Epic 2 | Audio diagnostic utility |
| FR39 | Epic 2 | CPU performance governor tuning script |

## Epic List

### Epic 1: Clean Architecture Foundation
After this epic the developer can navigate the codebase with confidence — all interfaces reside in one canonical location, the voice pipeline continues working end-to-end, every tool dispatch uses structural pattern matching, the full test suite runs without physical hardware, and the developer can locate any interface definition without tracing import chains.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR16, FR25, FR26, FR27, FR28, FR29, FR33, FR34, FR35, FR36
**Phase:** Phase 1

### Epic 2: Pipeline Observability & Performance Gates
After this epic the operator can deploy to Pi 5 and mechanically verify both Phase 1 gate conditions — `PipelineMetrics` are emitted per utterance as structured JSON, per-stage latency is diagnosable, the model sweep benchmark identifies the optimal GGUF + thread configuration, and worker errors surface in the same output stream.
**FRs covered:** FR21, FR22, FR23, FR24, FR37, FR38, FR39
**Phase:** Phase 1

### Epic 3: Autonomous Pomodoro Cycle
After this epic the user speaks one start command and the bot autonomously drives the complete Pomodoro cycle — 4 work sessions, short breaks, long break after session 4, cycle reset — with spoken German announcements at every transition boundary and live Web UI state updates, entirely without further manual commands.
**FRs covered:** FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15
**Phase:** Phase 2 (unlocked by Phase 1 AND gate)

### Epic 4: Tool Ecosystem & Oracle Integration
After this epic the developer has proved the ≤2-file tool-addition contract with a working `tell_joke` tool, and the existing oracle integrations (calendar events, air quality, ambient light) optionally enrich LLM context while degrading gracefully when unavailable.
**FRs covered:** FR17, FR18, FR19, FR20, FR30, FR31, FR32
**Phase:** Phase 2 (unlocked by Phase 1 AND gate)

---

## Epic 1: Clean Architecture Foundation

After this epic the developer can navigate the codebase with confidence — all interfaces reside in one canonical location, the voice pipeline continues working end-to-end, every tool dispatch uses structural pattern matching, the full test suite runs without physical hardware, and the developer can locate any interface definition without tracing import chains.

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR16, FR25, FR26, FR27, FR28, FR29, FR33, FR34, FR35, FR36
**Phase:** Phase 1

---

### Story 1.1: Contracts Layer Consolidation

As a developer,
I want all Protocol definitions and IPC envelope types consolidated into a single `src/contracts/` namespace,
So that I can locate any interface without tracing import chains and "where does a new interface go?" has one unambiguous answer.

**Acceptance Criteria:**

**Given** `src/runtime/contracts.py` and `src/oracle/contracts.py` contain Protocol definitions
**When** the consolidation is complete
**Then** `STTClient`, `LLMClient`, `TTSClient` Protocol definitions exist in `src/contracts/pipeline.py`
**And** `src/runtime/contracts.py` is dissolved — the file no longer exists
**And** `src/oracle/contracts.py` contents are absorbed into `src/contracts/pipeline.py` or `src/contracts/oracle.py`
**And** all import sites throughout the codebase are updated to import from `src/contracts/`

**Given** `_RequestEnvelope` and `_ResponseEnvelope` are buried inside `_ProcessWorker` internals
**When** the consolidation is complete
**Then** both types exist in `src/contracts/ipc.py` as `@dataclass(frozen=True, slots=True)` typed dataclasses
**And** `_ProcessWorker` imports them from `src/contracts/ipc.py` — no local definition remains

**Given** the consolidation is complete
**When** `uv run pytest tests/runtime/test_contract_guards.py` is executed
**Then** all guard tests pass with no violations
**And** `uv run pytest tests/` passes in full — no regressions introduced

---

### Story 1.2: Configuration Boundary Enforcement

As a developer,
I want the three config files to have explicit, non-overlapping responsibilities with no I/O in schema or parser files,
So that config logic has a single owner and I can navigate config concerns without confusion about which file is authoritative.

**Acceptance Criteria:**

**Given** `app_config_schema.py`, `app_config_parser.py`, and `app_config.py` exist
**When** the boundary enforcement is complete
**Then** `app_config_schema.py` contains only pure dataclasses (`AppConfig`, `SecretConfig`, `*Settings`) with zero I/O — no file reads, no `os.getenv` calls
**And** `app_config_parser.py` contains only the TOML bytes → typed config logic with zero I/O — accepts `bytes`, returns typed config, no file reads
**And** `app_config.py` is the sole location for all I/O: file reading, `os.getenv`, `PICO_VOICE_ACCESS_KEY` loading, and the `getattr(sys, "frozen", False)` frozen-binary guard

**Given** the CPU core assignment configuration exists
**When** a developer reads `config.toml`
**Then** `[stt] cpu_cores`, `[llm] cpu_cores`, and `[tts] cpu_cores` keys are clearly documented with their defaults
**And** the `APP_CONFIG_FILE` environment variable override is respected — the system loads config from the path specified in that variable when set

**Given** the boundary enforcement is complete
**When** `uv run pytest tests/` is executed
**Then** all tests pass with no regressions

---

### Story 1.3: LLM Module Boundaries & Module Naming Corrections

As a developer,
I want each LLM module to have a single, clearly named responsibility with no overlapping logic,
So that parser changes carry no risk of regressions in inference logic and I can open any LLM file knowing exactly what it does.

**Acceptance Criteria:**

**Given** the LLM module boundary enforcement is complete
**When** a developer inspects `llm/llama_backend.py`
**Then** it contains only llama.cpp wrapper logic, GBNF grammar setup, and raw inference → raw string output
**And** it contains no JSON parsing logic and no command routing logic

**Given** the LLM module boundary enforcement is complete
**When** a developer inspects `llm/parser.py`
**Then** it contains only raw string → `StructuredResponse` JSON normalisation and intent fallback logic
**And** it contains no llama.cpp calls and no command routing logic

**Given** the LLM module boundary enforcement is complete
**When** a developer inspects `llm/fast_path.py`
**Then** it contains only deterministic German command routing, returning `StructuredResponse | None`
**And** it contains no llama.cpp calls and no JSON parsing logic

**Given** the LLM module boundary enforcement is complete
**When** a developer inspects `llm/service.py`
**Then** it contains only orchestration: `fast_path → llama_backend → parser`
**And** it contains no parsing logic and no grammar setup logic

**Given** any module in `src/` has a name that does not accurately describe its responsibility
**When** the naming corrections are complete
**Then** all module names accurately describe the single responsibility of their contents
**And** no module name shadows a stdlib or third-party package name

**Given** the boundary enforcement and naming corrections are complete
**When** `uv run pytest tests/runtime/test_contract_guards.py` is executed
**Then** all guard tests pass, including any new guards added to enforce LLM module boundaries
**And** `uv run pytest tests/` passes in full — no regressions introduced

---

### Story 1.4: Frozen Value Objects & Structural Pattern Matching Dispatch

As a developer,
I want all high-frequency value objects to use `@dataclass(frozen=True, slots=True)` and tool dispatch to use structural pattern matching,
So that per-instance `__dict__` allocation is eliminated on high-frequency IPC construction and adding a new tool requires only one `case` arm addition.

**Acceptance Criteria:**

**Given** the frozen value object migration is complete
**When** a developer inspects any high-frequency value object (IPC envelopes, metrics payloads, LLM response types)
**Then** every such type is decorated with `@dataclass(frozen=True, slots=True)`
**And** no high-frequency value object uses plain `@dataclass` without `slots=True`

**Given** the dispatch refactor is complete
**When** a developer inspects `runtime/tools/dispatch.py`
**Then** `RuntimeToolDispatcher` uses a `match tool_call.name:` structural pattern matching statement
**And** there are no `if/elif` chains in the dispatch path
**And** each `case` arm calls a single handler function

**Given** the dispatch refactor is complete
**When** a new tool name constant is added to `src/contracts/tool_contract.py`
**Then** a single `case` arm added to `dispatch.py` is the only required dispatch change — no other file in the dispatch path requires modification

**Given** the `ToolName` Literal type is defined in `src/contracts/tool_contract.py`
**When** `uv run pytest tests/runtime/test_contract_guards.py` is executed
**Then** all guard tests pass, including enforcement that no `if/elif` dispatch chains exist in guarded paths
**And** `uv run pytest tests/` passes in full — no regressions introduced

---

### Story 1.5: Hardware-Free Test Suite Verification

As a developer,
I want the complete test suite to pass without physical audio hardware, ML model files, wake-word model files, or network access,
So that I can run `uv run pytest tests/` on any development machine and trust the result as a valid regression baseline.

**Acceptance Criteria:**

**Given** the test suite is run on a machine with no Raspberry Pi hardware, no GGUF model files, no `.ppn`/`.pv` wake-word files, and no network connection
**When** `uv run pytest tests/` is executed
**Then** all tests pass with zero failures and zero errors
**And** no test attempts to load a real llama-cpp-python, faster-whisper, piper, or pvporcupine model

**Given** each ML worker has a public Protocol-backed interface (`STTClient`, `LLMClient`, `TTSClient`)
**When** a developer writes a test for any module that depends on an ML worker
**Then** the worker can be replaced with a `sys.modules` stub or Protocol-conforming test double — no real subprocess spawn is required
**And** the test double is sufficient to exercise the full logic of the module under test

**Given** all structural changes from Stories 1.1–1.4 are complete
**When** `uv run pytest tests/` is executed
**Then** the voice pipeline integration behaviour (FR1–5 sequential execution, FR6 fast-path routing) is verified by existing tests without hardware
**And** the WebSocket UI event/state constants (FR33–35) are verified by existing tests using `src/contracts/ui_protocol.py` constants — no inline strings
**And** the guard tests in `tests/runtime/test_contract_guards.py` all pass, enforcing all architectural invariants established in this epic

---

## Epic 2: Pipeline Observability & Performance Gates

After this epic the operator can deploy to Pi 5 and mechanically verify both Phase 1 gate conditions — `PipelineMetrics` are emitted per utterance as structured JSON, per-stage latency is diagnosable, the model sweep benchmark identifies the optimal GGUF + thread configuration, and worker errors surface in the same output stream.

**FRs covered:** FR21, FR22, FR23, FR24, FR37, FR38, FR39
**Phase:** Phase 1

---

### Story 2.1: PipelineMetrics Typed Dataclass & Structured JSON Log Emission

As a developer,
I want a typed `PipelineMetrics` dataclass emitted per utterance as structured JSON to the log output,
So that I can verify performance gates mechanically from log output and diagnose which pipeline stage is slow without printf debugging.

**Acceptance Criteria:**

**Given** an utterance cycle completes
**When** `PipelineMetrics` is emitted
**Then** it is a `@dataclass(frozen=True, slots=True)` with fields: `stt_ms: int`, `llm_ms: int`, `tts_ms: int`, `tokens: int`, `tok_per_sec: float`, `e2e_ms: int`
**And** it is emitted synchronously — no buffering, no batch aggregation — immediately after the utterance cycle completes
**And** `logger.info(metrics.to_json())` produces exactly: `{"event": "pipeline_metrics", "stt_ms": N, "llm_ms": N, "tts_ms": N, "tokens": N, "tok_per_sec": F, "e2e_ms": N}`

**Given** `PipelineMetrics` is defined in `llm/types.py`
**When** a developer writes a unit test for metrics emission
**Then** the test can assert the correct JSON output without executing an end-to-end utterance cycle
**And** the test requires no hardware, no model files, and no real subprocess spawn

**Given** a fast-path utterance bypasses LLM inference
**When** `PipelineMetrics` is emitted
**Then** `llm_ms` is `0` and `tokens` is `0` — fast-path bypasses LLM cleanly without leaving metric fields undefined

---

### Story 2.2: Worker Error Structured Logging

As a developer,
I want worker errors surfaced in the same structured log stream as `PipelineMetrics` with the main process remaining alive and recoverable,
So that I can diagnose which worker failed and why without the daemon crashing and requiring a manual restart.

**Acceptance Criteria:**

**Given** an ML worker subprocess (STT, LLM, or TTS) raises an exception during an utterance cycle
**When** the exception propagates to the main process
**Then** the main process does not terminate — it catches the exception and logs a structured error entry
**And** the structured error log entry appears at the same log level as `PipelineMetrics` output
**And** the log entry identifies the failing worker and includes the exception message

**Given** a `WorkerCallTimeoutError` is raised
**When** it is caught by the pipeline orchestration
**Then** it is logged as a structured entry with `"event": "worker_timeout"` and the worker name
**And** the system returns to an idle, ready-for-next-utterance state

**Given** a `WorkerCrashError` is raised
**When** it is caught by the pipeline orchestration
**Then** it is logged as a structured entry with `"event": "worker_crash"` and the worker name
**And** the system returns to an idle, ready-for-next-utterance state

**Given** a `WorkerTaskError` is raised
**When** it is caught by the pipeline orchestration
**Then** it is logged as a structured entry with `"event": "worker_task_error"` and the worker name
**And** the system returns to an idle, ready-for-next-utterance state

**Given** worker error logging is implemented
**When** `uv run pytest tests/` is executed
**Then** all error handling paths are covered by unit tests using worker stubs — no real subprocesses required

---

### Story 2.3: LLM Model Sweep Benchmark Tooling

As an operator,
I want a benchmark tool that sweeps GGUF quantisations and thread counts and outputs machine-readable results,
So that I can identify the optimal model configuration for Pi 5 without manual trial-and-error across variants.

**Acceptance Criteria:**

**Given** the benchmark tool is run on Pi 5
**When** it executes a model sweep
**Then** it tests all combinations of: quantisations (Q4_K_M, Q5_K_M, Q8_0) × thread counts (2, 3, 4)
**And** for each combination it measures tokens/second and end-to-end latency across a minimum of 3 representative utterances
**And** it outputs results as JSON to `build/benchmark_results.json`

**Given** `build/benchmark_results.json` exists after a sweep run
**When** a developer reads the file
**Then** each entry contains: `model_variant`, `n_threads`, `tok_per_sec`, `e2e_ms`, and `utterance_count`
**And** the entries are sortable by `tok_per_sec` to identify the optimal configuration immediately

**Given** the CPU performance governor is set to `performance` via `./scripts/pi5_cpu_tuning.sh apply`
**When** the benchmark is run
**Then** results reflect consistent throughput with no frequency-scaling spikes — the tuning script is documented as a prerequisite step

**Given** the audio diagnostic utility exists at `src/debug/audio_diagnostic.py`
**When** an operator runs it
**Then** it provides ALSA device selection guidance and VAD threshold tuning output — assisting with accurate STT timing in benchmark conditions

---

### Story 2.4: Phase 1 Performance Gate Verification on Pi 5

As an operator,
I want to deploy the Phase 1 build to Pi 5, apply the optimal benchmark configuration, and verify both performance gates are met,
So that Phase 2 work can begin with confidence that the foundation meets its quantified targets.

**Acceptance Criteria:**

**Given** the optimal GGUF quantisation and thread count are identified from Story 2.3 benchmark results
**When** `config.toml` is updated with the optimal values and the system is restarted
**Then** `PipelineMetrics` log output shows `tok_per_sec >= 10.0` across a minimum of 3 representative utterances
**And** `PipelineMetrics` log output shows `e2e_ms <= 25000` across those same utterances

**Given** both performance gates are met
**When** the benchmark results JSON is committed to `build/`
**Then** the commit message identifies the model variant, thread count, measured tok/s, and measured e2e latency
**And** the repository is tagged `v1.0.0-phase1-verified`

**Given** the Phase 1 build is deployed
**When** the operator runs `sudo systemctl restart pomodoro-bot`
**Then** the daemon starts successfully as a persistent background service managed by systemd
**And** structured `PipelineMetrics` JSON appears in the system log on first utterance
**And** the `EnvironmentFile=` directive loads secrets from `.env` without them appearing in `config.toml`

**Given** both performance gates are met AND all tests from Epic 1 pass AND contracts are consolidated
**Then** all three Phase 1 AND gate conditions are satisfied and Phase 2 work may begin

---

## Epic 3: Autonomous Pomodoro Cycle

After this epic the user speaks one start command and the bot autonomously drives the complete Pomodoro cycle — 4 work sessions, short breaks, long break after session 4, cycle reset — with spoken German announcements at every transition boundary and live Web UI state updates, entirely without further manual commands.

**FRs covered:** FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15
**Phase:** Phase 2 (unlocked by Phase 1 AND gate)

---

### Story 3.1: Manual Pomodoro Session Control

As a user,
I want to start, stop, and query a Pomodoro session via voice command,
So that I can initiate and control focus sessions hands-free with spoken German confirmations.

**Acceptance Criteria:**

**Given** the assistant is idle and no Pomodoro session is active
**When** the user says a start command (e.g. "Starte eine Pomodoro-Session")
**Then** the `PomodoroTimer` transitions to the `running` state with the work phase active
**And** the TTS speaks a German confirmation (e.g. "Pomodoro gestartet. 25 Minuten Fokuszeit.")
**And** the session start time is recorded for accurate phase timing

**Given** a Pomodoro session is active
**When** the user says a stop command (e.g. "Stoppe die Pomodoro-Session")
**Then** the `PomodoroTimer` transitions to `idle` state and all timers are cancelled
**And** the TTS speaks a German confirmation (e.g. "Pomodoro-Session beendet.")
**And** session state is fully reset — a subsequent start command begins a fresh cycle

**Given** a Pomodoro session is active
**When** the user says a status query (e.g. "Wie lange läuft die Session schon?")
**Then** the TTS speaks the current phase and elapsed time in German (e.g. "Erste Fokuseinheit, noch 18 Minuten.")
**And** the response is generated without disrupting the running phase timer

**Given** no Pomodoro session is active
**When** the user says a stop or status command
**Then** the TTS speaks an appropriate German response indicating no active session
**And** the system remains in idle state — no error or crash

**Given** Pomodoro voice commands are implemented
**When** `uv run pytest tests/` is executed
**Then** all `PomodoroTimer` state transitions are covered by unit tests using stubs — no hardware or real timers required

---

### Story 3.2: Autonomous Work-Break Phase Transitions

As a user,
I want the bot to automatically announce and transition between work and short break phases without any manual command,
So that I can focus entirely on my work without watching a timer or interacting with the assistant between phases.

**Acceptance Criteria:**

**Given** a Pomodoro work phase is active (25 minutes by default)
**When** the configured work duration expires
**Then** the bot autonomously announces the transition in German (e.g. "Erste Pomodoro-Einheit abgeschlossen. Kurze Pause — fünf Minuten.")
**And** the `PomodoroTimer` transitions to the `short_break` state without any user command
**And** the session count increments by one

**Given** a short break phase is active (5 minutes by default)
**When** the configured short break duration expires
**Then** the bot autonomously announces the return to work in German (e.g. "Pause vorbei. Zweite Fokuseinheit beginnt jetzt.")
**And** the `PomodoroTimer` transitions back to the `work` state without any user command

**Given** the transition logic uses the `runtime/ticks.py` tick handler
**When** a phase transition fires
**Then** it does not require a user utterance to trigger — it is driven by an internal timer callback
**And** the sequential pipeline order (wake-word → STT → LLM → TTS) is preserved — the announcement uses the TTS worker directly via the tick handler path, not via the full utterance pipeline

**Given** autonomous transitions are implemented
**When** `uv run pytest tests/` is executed
**Then** work→break and break→work transitions are exercisable in unit tests with a time-stubbed `PomodoroTimer` — no real 25-minute wait required

---

### Story 3.3: Long Break & Full Cycle Reset

As a user,
I want the bot to automatically trigger a long break after my 4th work session and reset the cycle afterwards,
So that the full Pomodoro method runs without me tracking session count or initiating any action after the first start command.

**Acceptance Criteria:**

**Given** three work sessions and three short breaks have completed autonomously
**When** the 4th work session duration expires
**Then** the bot speaks a German long break announcement (e.g. "Vier Einheiten abgeschlossen. Lange Pause — fünfzehn Minuten. Gut gemacht.")
**And** the `PomodoroTimer` transitions to `long_break` state with a 15-minute timer
**And** no short break is triggered after session 4 — the long break fires instead

**Given** a long break phase is active (15 minutes by default)
**When** the long break duration expires
**Then** the bot speaks a German cycle reset announcement (e.g. "Lange Pause vorbei. Neuer Zyklus beginnt.")
**And** the `PomodoroTimer` resets to session count 1 and transitions to `work` state
**And** the full 4-session cycle repeats from the beginning without any user command

**Given** the full cycle (4 × work + 3 × short break + 1 × long break + reset) runs end-to-end
**When** each transition fires
**Then** a spoken German announcement accompanies every boundary — no silent transitions
**And** the system state is consistent at every boundary: session count, phase, and timer values are correct

**Given** long break and cycle reset logic is implemented
**When** `uv run pytest tests/pomodoro/` is executed
**Then** the full 4-session cycle is exercisable with a stubbed timer — session count, phase sequence, and announcement triggers are all verified without real elapsed time

---

### Story 3.4: Web UI Pomodoro State Synchronisation

As a user,
I want the browser UI to reflect the current Pomodoro phase and session count in real time at every transition,
So that I can glance at my side monitor and immediately see where I am in the cycle without asking the assistant.

**Acceptance Criteria:**

**Given** a Pomodoro session is started via voice command
**When** the `PomodoroTimer` transitions to `work` state
**Then** the `RuntimeUIPublisher` broadcasts a WebSocket state update with the current phase (`STATE_POMODORO_WORK` or equivalent constant from `contracts/ui_protocol.py`) and session count
**And** all connected browser clients update their displayed state within one WebSocket message round-trip

**Given** an autonomous phase transition occurs (work→break, break→work, work→long break, long break→reset)
**When** the transition fires in `runtime/ticks.py`
**Then** a WebSocket state update is broadcast immediately after the TTS announcement is queued
**And** the UI state constant used is always from `src/contracts/ui_protocol.py` — never an inline string

**Given** a Pomodoro session is stopped via voice command
**When** the `PomodoroTimer` transitions to `idle`
**Then** the UI receives a WebSocket update reflecting the idle state
**And** the session count displayed resets to reflect the cleared state

**Given** a browser client connects to `ws://localhost:8765` while a session is in progress
**When** the connection is established
**Then** the client receives the current phase and session count on connect — it does not have to wait for the next transition to get accurate state

**Given** the WebSocket state synchronisation is implemented
**When** `uv run pytest tests/` is executed
**Then** all UI broadcast calls are verified by tests using a mock `RuntimeUIPublisher` — no real WebSocket connection required

---

## Epic 4: Tool Ecosystem & Oracle Integration

After this epic the developer has proved the ≤2-file tool-addition contract with a working `tell_joke` tool, and the existing oracle integrations (calendar events, air quality, ambient light) optionally enrich LLM context while degrading gracefully when unavailable.

**FRs covered:** FR17, FR18, FR19, FR20, FR30, FR31, FR32
**Phase:** Phase 2 (unlocked by Phase 1 AND gate)

---

### Story 4.1: Pure-LLM Tool — `tell_joke`

As a developer,
I want to add a `tell_joke` tool by modifying exactly 2 source files,
So that the ≤2-file tool-addition contract established in Epic 1 is proved with a real working tool.

**Acceptance Criteria:**

**Given** the contracts and dispatch architecture from Epic 1 is stable
**When** the `tell_joke` tool is implemented
**Then** exactly 2 source files are modified: `src/contracts/tool_contract.py` and `runtime/tools/dispatch.py`
**And** no other source file requires modification for the tool to function

**Given** `src/contracts/tool_contract.py` is updated
**When** a developer inspects the file
**Then** a `TOOL_TELL_JOKE` constant is defined
**And** `"tell_joke"` is appended to `TOOL_NAME_ORDER` in the correct position
**And** `"tell_joke"` is added to `TOOLS_WITHOUT_ARGUMENTS` — the tool takes no arguments, omitting this causes malformed GBNF grammar

**Given** `runtime/tools/dispatch.py` is updated
**When** a developer inspects the dispatch match statement
**Then** a single `case TOOL_TELL_JOKE:` arm exists that calls a `handle_tell_joke` handler
**And** the handler returns a `StructuredResponse` with a German joke as `assistant_text`
**And** no external dependency, oracle call, or subprocess spawn is required by the handler

**Given** `tell_joke` is dispatched
**When** the user says the German trigger phrase (e.g. "Erzähl mir einen Witz")
**Then** the fast-path in `llm/fast_path.py` routes the deterministic phrase directly to the handler — no LLM inference required
**And** TTS speaks the German joke response
**And** `PipelineMetrics` reflects `llm_ms: 0` and `tokens: 0` for the fast-path route

**Given** `tell_joke` is implemented
**When** `uv run pytest tests/` is executed
**Then** all tests pass including a new unit test for `handle_tell_joke` that requires no model files or subprocesses

---

### Story 4.2: Calendar Oracle Context Enrichment

As a user,
I want the assistant to optionally enrich its LLM context with my upcoming calendar events when I ask time-aware questions,
So that the assistant can give contextually relevant responses about my schedule while degrading cleanly when the calendar is unavailable.

**Acceptance Criteria:**

**Given** the Google Calendar oracle is configured (service account JSON path set in `.env`)
**When** the user asks a question that triggers the calendar tool (e.g. "Was steht heute noch an?")
**Then** `OracleContextService` retrieves upcoming calendar events and includes them in the LLM prompt context
**And** the LLM generates a response that references the actual calendar data
**And** the TTS speaks the response in German

**Given** the Google Calendar oracle is configured and available
**When** `OracleContextService.get()` is called
**Then** it returns calendar event data within a reasonable timeout
**And** the data is included in the `EnvironmentContext` passed to the LLM worker

**Given** the Google Calendar oracle is unavailable (network down, misconfigured, or credentials absent)
**When** the user asks a calendar-related question
**Then** the voice pipeline completes the full utterance cycle without error or crash
**And** the LLM receives an `EnvironmentContext` with no calendar data — it responds gracefully without calendar context
**And** no exception from the calendar integration propagates to terminate the pipeline

**Given** the calendar oracle integration is implemented
**When** `uv run pytest tests/oracle/` is executed
**Then** both the available and unavailable oracle paths are covered by unit tests using stubs — no real Google API calls required

---

### Story 4.3: Sensor Oracle Context Enrichment

As a user,
I want the assistant to optionally enrich its responses with air quality and ambient light sensor readings when relevant,
So that the assistant can give context-aware responses about my environment while degrading cleanly when sensors are absent.

**Acceptance Criteria:**

**Given** an ENS160 air quality sensor is connected via I²C
**When** the user asks an environment-related question (e.g. "Wie ist die Luftqualität?")
**Then** `OracleContextService` retrieves the current air quality reading and includes it in the LLM prompt context
**And** the LLM generates a response referencing the sensor reading
**And** the TTS speaks the response in German

**Given** a TEMT6000 ambient light sensor is connected via I²C and an ADS1115 ADC
**When** the user asks about the ambient light level
**Then** `OracleContextService` retrieves the ambient light reading and includes it in the LLM prompt context
**And** the LLM generates a response referencing the light level

**Given** either sensor is absent, disconnected, or the oracle is disabled in config
**When** the user asks any question — environment-related or otherwise
**Then** the voice pipeline completes the full utterance cycle without error or crash
**And** the LLM receives an `EnvironmentContext` with the missing sensor field as `None`
**And** no I²C exception or sensor read error propagates to terminate the pipeline or produce a spoken error

**Given** both sensors are absent simultaneously
**When** any utterance is processed
**Then** the oracle degradation is silent — no warning is spoken to the user; the pipeline proceeds with available context only

**Given** the sensor oracle integration is implemented
**When** `uv run pytest tests/oracle/` is executed
**Then** sensor-available, sensor-absent, and partial-sensor (one present, one absent) paths are all covered by unit tests using stubs — no real I²C hardware required
**And** `uv run pytest tests/` passes in full with no regressions




---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish']
classification:
  projectType: iot_embedded
  domain: general_ml
  complexity: high
  projectContext: brownfield
  phase1: foundation_architecture_modernisation_metrics
  phase2: new_tools_extended_pomodoro
inputDocuments:
  - '_bmad-output/project-context.md'
  - 'docs/index.md'
  - 'docs/project-overview.md'
  - 'docs/architecture.md'
  - 'docs/source-tree-analysis.md'
  - 'docs/development-guide.md'
  - 'docs/deployment-guide.md'
briefCount: 0
researchCount: 0
brainstormingCount: 0
projectDocsCount: 7
workflowType: 'prd'
---

# Product Requirements Document — pomodoro-bot

**Author:** Shrink0r
**Date:** 2026-02-28

## Executive Summary

The north star of this initiative is a streaming-capable, structurally coherent pomodoro-bot. Today's fully-buffered pipeline (wake-word → STT → LLM → TTS) works correctly but buffers each stage to completion before handing off downstream — the user waits for the entire LLM response before synthesis begins. The target: TTS synthesis begins as the first LLM sentence lands, collapsing perceived latency on hardware where inference is measured in seconds. That streaming future is only achievable cleanly if every pipeline stage boundary is Protocol-defined, composable, and independently testable today. This PRD defines the work that gets there.

pomodoro-bot is a local-first, privacy-preserving voice assistant running the complete ML pipeline — wake-word detection, speech transcription, LLM inference, TTS synthesis — on a Raspberry Pi 5 without cloud dependencies. It is pre-production: no backward compatibility constraints apply, no migration strategies are required, and the team has full structural freedom to reorganise module boundaries, rename packages, revise constructor signatures, and restructure the contracts layer without downstream consequences.

The initiative is structured as a **two-phase gate**:

**Phase 1 — Foundation** resolves identified structural incoherence and establishes a measurable performance baseline. Structural problems to address: three disjoint contracts namespaces (`src/contracts/`, `src/runtime/contracts.py`, `src/oracle/contracts.py`) with no consistent ownership rule; config logic split across three files with blurry boundaries; LLM parser fragmented into four files with overlapping names; IPC envelope types buried inside the worker base class rather than defined as first-class contracts; misleading module names (`runtime/tools/messages.py`, `src/stt/stt.py`). All external dependencies must be behind Protocol boundaries in a single coherent contracts layer. All object construction must surface at the composition root. Modern Python 3.13 idioms applied where they carry measurable benefit: `@dataclass(frozen=True, slots=True)` eliminates per-instance `__dict__` allocation on high-frequency IPC envelope construction — a meaningful gain at Pi 5 scale. A typed `PipelineMetrics` dataclass, emitted per utterance, replaces the current string-logged `stt_ms`/`llm_ms`/`tts_ms` values — designed for dual consumption: structured log output and a future programmatic sink (e.g. rolling latency display in the web UI).

**The inviolable constraint across both phases:** the sequential interaction flow — **wake-word → STT → LLM → TTS** — must not change. Refactoring improves the internal structure of each stage and the contracts between them; it does not alter pipeline execution order or introduce concurrency between stages.

**Phase 1 is gated on three AND conditions:** ≥ 10 tokens/second LLM throughput on Pi 5; ≤ 25 seconds end-to-end latency (wake-word → spoken response); contracts consolidated and modern idioms applied. All three must be true before Phase 2 begins.

**Phase 2 — Features** adds new tool calls and extends the Pomodoro session flow, enabled cleanly by the contracts and composition improvements from Phase 1.

Existing architectural rules in `project-context.md` serve as **design intent**, not hard constraints — they may be revised where the refactoring surface reveals superior patterns.

### What Makes This Special

pomodoro-bot operates in a space almost entirely occupied by cloud-dependent products. Fully local ML inference on a €80 single-board computer, German-language wake-word and TTS, zero network calls in the voice pipeline, and a live browser UI pushed over WebSocket — there is no comparable open-source equivalent at this integration level.

When streaming lands, the user hears the first spoken word while the model is still generating. On constrained hardware where inference takes seconds, this transforms "wait and receive" into conversational response — achieved entirely locally. Phase 1 is the direct prerequisite.

## Project Classification

| Property | Value |
|----------|-------|
| **Project Type** | `iot_embedded` — voice assistant daemon targeting Raspberry Pi 5 ARM64 |
| **Domain** | General productivity / on-device ML (no regulatory requirements) |
| **Complexity** | High — full structural freedom (pre-production) but real-time audio pipeline and constrained hardware throughout |
| **Project Context** | Brownfield, pre-production — no backward compatibility, no migrations |
| **Inviolable Constraint** | Pipeline order wake-word → STT → LLM → TTS must not change |
| **Phase 1 Performance Gate** | ≥ 10 tok/s LLM throughput; ≤ 25s end-to-end latency (wake-word → speech) |
| **Delivery Model** | PyInstaller one-file arm64 binary distributed via GitHub Releases |

## Success Criteria

### User Success

**As developer:** The codebase is navigable with confidence. Adding a new tool call touches at most 2–3 files — the tool contract, the dispatch handler, and optionally the system prompt — with no archaeology required. The dependency graph is readable without tracing imports; the composition root tells the whole story.

**As end user:** The assistant is measurably more responsive — performance gates are met and felt. The full Pomodoro cycle runs autonomously: work phases transition to breaks, breaks transition back, the long break triggers after the 4th session, and spoken announcements accompany every transition without manual commands.

### Business Success

Business success is defined as unlocking the streaming north star: when Phase 1 is complete, implementing streaming LLM → TTS is a tractable, scoped engineering task — not an architectural intervention. The refactored codebase is the asset; streaming responsiveness is the return on it.

### Technical Success

**Phase 1 — all three conditions required before Phase 2 begins (AND gate):**

1. **Performance gate:** ≥ 10 tokens/second LLM throughput on Raspberry Pi 5; ≤ 25 seconds end-to-end latency (wake-word → first spoken word), measured under representative load using the existing benchmarking tooling.

2. **Contracts consolidated:** A single canonical location owns all Protocol and interface definitions. `src/runtime/contracts.py` and `src/oracle/contracts.py` are dissolved into the unified contracts layer. The answer to "where does a new interface go?" is unambiguous.

3. **Modern idioms applied systematically:** All high-frequency value objects use `@dataclass(frozen=True, slots=True)`. IPC envelope types (`_RequestEnvelope`, `_ResponseEnvelope`) are first-class typed contracts. `PipelineMetrics` is a typed dataclass emitted per utterance, consumed by the structured logger and registerable sinks. Structural pattern matching replaces `if/elif` dispatch chains where applicable.

**Phase 2 — all of the following:**

- Full Pomodoro cycle: 4 × (25min work + 5min short break) → long break → cycle reset; bot drives all transitions autonomously with spoken announcements.
- ≤ 5 new tool calls added, each requiring changes to at most 2–3 files.
- All existing tests pass after every change. No regression in existing functionality.
- Sequential pipeline order (wake-word → STT → LLM → TTS) preserved without exception.

### Measurable Outcomes

| Outcome | Measure | Gate |
|---------|---------|------|
| LLM throughput | ≥ 10 tok/s on Pi 5 | Phase 1 |
| E2E latency | ≤ 25s wake-word → speech | Phase 1 |
| Contracts location | 1 canonical namespace | Phase 1 |
| New tool addition cost | ≤ 3 files changed | Phase 1 |
| Test suite | 100% pass rate | Both phases |
| Pomodoro cycle | Full 4-session cycle autonomous | Phase 2 |
| New tools | ≤ 5 additions | Phase 2 |
| Pipeline order | wake-word → STT → LLM → TTS | Both phases |

## User Journeys

### Journey 1 — Voice User: The Full Pomodoro Session (Happy Path)

**Persona:** Shrink0r, mid-afternoon, sitting at the desk where the Pi 5 lives. A task needs deep work. The phone is face-down. The goal is 90 minutes of uninterrupted focus — two full Pomodoro cycles without touching a keyboard.

**Opening Scene:** He says "Hey Pomo." The wake-word fires. Within a second, the Miro UI flickers to active in the browser tab he keeps open on the side monitor. He says "Starte eine Pomodoro-Session." The LLM routes to `start_pomodoro`. TTS confirms: "Pomodoro gestartet. 25 Minuten Fokuszeit." The session is live.

**Rising Action:** Twenty-three minutes pass. He hasn't touched anything. At minute 25, the bot speaks unprompted: "Erste Pomodoro-Einheit abgeschlossen. Kurze Pause — fünf Minuten." The UI updates. He gets up, makes coffee. He doesn't say a word. At five minutes, the bot: "Pause vorbei. Zweite Fokuseinheit beginnt jetzt." He sits back down. This repeats — session 2, break 2, session 3, break 3, session 4. After the fourth session, the bot: "Vier Einheiten abgeschlossen. Lange Pause — fünfzehn Minuten. Gut gemacht." The full cycle, driven entirely by the bot, without a single manual command after the first.

**Climax:** The long break fires automatically. The cycle resets without prompting. No manual intervention, no watching a timer, no cognitive overhead from the tool itself. The Pomodoro method is working as designed.

**Resolution:** Ninety minutes later, Shrink0r has completed two full cycles. The UI shows session history. He said three words to start it. The assistant did everything else.

**Requirements revealed:** Autonomous phase transition engine; spoken announcements at every transition boundary; long break trigger after 4th session; cycle reset; session state survives between phases; UI reflects phase state in real time.

---

### Journey 2 — Developer: Adding a New Tool Call (Phase 1 Success Scenario)

**Persona:** Shrink0r, post-Phase-1, looking at the codebase with the confidence that "this is the foundation I want to build on." He wants to add a `tell_joke` tool — speak "Erzähl mir einen Witz" and get a spoken joke from the LLM. No oracle. No sensor. Pure prompt + dispatch.

**Opening Scene:** He opens `src/contracts/tool_contract.py`. `TOOL_NAME_ORDER` is right there — the canonical list. He adds `"tell_joke"` in the right position. One file, one line.

**Rising Action:** He opens `src/runtime/tools/dispatch.py`. The routing table is clean — a match statement, each arm calling a handler. He adds one arm: `case "tell_joke": return await handle_tell_joke(context)`. He adds `handle_tell_joke` in the same file — it returns a TTS response string directly; no external dependency needed. He opens `prompts/system_prompt.md` and adds a two-sentence tool description. He runs `uv run pytest tests/`. All pass. He adds a fast-path rule in `src/llm/fast_path.py` for the deterministic German phrase. Green.

**Climax:** Two files changed: `tool_contract.py` and `dispatch.py`. The system prompt update is optional polish. The minimal-case tool addition took under 15 minutes. No archaeology. No hidden instantiation to hunt. No second contracts namespace to check. The tool works on first test run.

**Resolution:** `tell_joke` ships. The "≤ 3 files" success criterion is validated at the minimal boundary — 2 files for a pure-LLM tool, 3 for tools with external dependencies. The contracts foundation delivers exactly the friction reduction it promised.

**Requirements revealed:** Single contracts namespace; structural pattern matching dispatch; hardware-free test suite; fast-path hook; minimal-case tool addition requires 2 file changes.

---

### Journey 3 — Operator: Pi 5 Setup and Performance Gate Verification

**Persona:** Shrink0r, fresh Raspberry Pi OS install, deploying a Phase 1 release. The goal: hit the performance gates and confirm structured metrics are flowing before declaring Phase 1 done.

**Opening Scene:** He downloads `archive-arm64.tar.gz` from the GitHub Release triggered by the `v1.0.0` tag. Extracts. Places Picovoice model files, Qwen3 GGUF, Thorsten piper model. Edits `config.toml` — two required fields. Sets `PICO_VOICE_ACCESS_KEY` in `.env`. Runs `./main`.

**Rising Action:** First utterance goes through. He checks the log output. Instead of `INFO stt_ms=1203 llm_ms=8400 tts_ms=950`, he sees: `{"event": "pipeline_metrics", "stt_ms": 1203, "llm_ms": 8400, "tts_ms": 950, "tokens": 47, "tok_per_sec": 5.6, "e2e_ms": 11200}`. Token throughput: 5.6 tok/s. Below gate. He runs `sudo ./scripts/pi5_cpu_tuning.sh apply`, restarts, reruns. `{"tok_per_sec": 8.1, "e2e_ms": 18400}`. Still below. He runs the model sweep — Q4_K_M vs Q5_K_M vs Q8_0 across 2, 3, 4 threads. Q4_K_M at 4 threads: 11.2 tok/s. E2E: 22.1s.

**Climax:** Both gates green: 11.2 tok/s ≥ 10, 22.1s ≤ 25. `PipelineMetrics` made the diagnosis mechanical — no printf debugging, no guessing. The benchmark tooling did the comparison. Phase 1 is verifiably done.

**Resolution:** He updates the config to 4-thread Q4_K_M, commits the benchmark JSON to `build/`, tags `v1.0.0-phase1-verified`. Phase 2 begins.

**Requirements revealed:** `PipelineMetrics` with `tok_per_sec` and `e2e_ms` fields; structured JSON log emission; model sweep tooling; CPU tuning scripts; config clarity for thread/core assignment.

---

### Journey 4 — Debugger: Tracking Down a Latency Spike

**Persona:** Shrink0r, three weeks into using the Phase 1 build, notices occasional utterances taking 40+ seconds. It's not consistent. He needs to find the stage where time is being lost.

**Opening Scene:** He triggers three utterances deliberately and watches the log. Two look normal: `{"tok_per_sec": 11.1, "e2e_ms": 21.3s}`. Third: `{"stt_ms": 14200, "llm_ms": 8100, "tts_ms": 940, "e2e_ms": 23.2s}`. The spike is in `stt_ms` — 14 seconds instead of the usual 1.2.

**Rising Action:** STT is the culprit. He opens `src/stt/config.py` — `vad_filter=True`, `beam_size=1`, `compute_type=int8`. All correct. He runs `uv run python src/debug/audio_diagnostic.py`. The VAD visualiser shows the microphone is picking up fan noise as speech, causing transcription to run on a very long audio segment before VAD trims it. He adjusts the VAD threshold in `config.toml`.

**Climax:** Re-runs three deliberate utterances. `stt_ms` back to 1.1–1.3s. `e2e_ms` back to 21–23s. `PipelineMetrics` told him exactly which stage to look at. The audio diagnostic tool showed him why. Two config lines fixed it.

**Resolution:** The structured metrics turned a vague "it's slow sometimes" into a diagnosable, fixable, verifiable problem.

**Requirements revealed:** Per-field latency in `PipelineMetrics` (`stt_ms`, `llm_ms`, `tts_ms` as separate fields); audio diagnostic utility accessible in release build; VAD configuration in `config.toml`; worker errors surfaced in structured log at same level as metrics.

---

### Journey Requirements Summary

| Journey | Key Capabilities Required |
|---------|--------------------------|
| Full Pomodoro Session | Autonomous phase engine; spoken transition announcements; long break after 4th session; cycle reset; UI state sync |
| Adding a New Tool (`tell_joke`) | Single contracts namespace; structural pattern matching dispatch; hardware-free test suite; fast-path hook; 2-file minimal tool addition |
| Performance Gate Verification | `PipelineMetrics` with `tok_per_sec` + `e2e_ms`; structured JSON log emission; model sweep tooling; CPU tuning scripts |
| Latency Spike Diagnosis | Per-stage latency fields in metrics; audio diagnostic tool; VAD config in `config.toml`; worker errors in structured log |

## Product Scope & Phased Development

### MVP Strategy

**Approach:** Platform foundation — Phase 1 delivers a refactored, measurably performant codebase the developer trusts as a base for future feature work. No external user base, no revenue model, no investor validation loop. Success criterion: "yes, this is the foundation I want to build on."

**Resource profile:** Solo developer, pre-production, full structural freedom. No backward compatibility. No migration costs.

### Phase 1 — Foundation (MVP)

**Core journeys supported:** Journey 2 (Developer: Adding a New Tool) and Journey 3 (Operator: Performance Gate Verification) are the primary beneficiaries. Journey 4 (Latency Spike Diagnosis) is fully enabled by `PipelineMetrics`. Journey 1 (Full Pomodoro Session) completes in Phase 2.

**Must-Have Capabilities (AND gate — all required for Phase 2 entry):**

| Capability | Rationale |
|-----------|-----------|
| Contracts layer consolidated to single namespace | Tool addition cost stays unpredictable until "where does a new interface go?" has an unambiguous answer |
| IPC envelope types promoted to first-class contracts | Streaming architecture preparation requires explicit, typed stage boundaries |
| `PipelineMetrics` typed dataclass with structured log output | Performance gates cannot be mechanically verified without it |
| `@dataclass(frozen=True, slots=True)` on high-frequency value objects | Measurable memory and allocation benefit at Pi 5 scale |
| Structural pattern matching in dispatch | Prerequisite for the "≤ 3 files" tool-addition success criterion |
| Config tripartite split resolved | Config ownership stays ambiguous until ownership boundaries are explicit |
| LLM parser fragmentation resolved | Parser changes remain risky while 4 files share overlapping responsibility |
| Misleading module names corrected | Developer navigation prerequisite for "no archaeology" criterion |
| Performance gates met: ≥ 10 tok/s, ≤ 25s e2e | Hard gate for Phase 2 entry; measured on Pi 5 under representative load |
| All tests passing | Regression baseline maintained throughout |

**Explicitly out of scope for Phase 1:** full Pomodoro cycle automation; new tool calls; streaming implementation; web UI changes.

### Phase 2 — Capability (Post-MVP)

Enabled by Phase 1 contracts and composition improvements:

- **Full Pomodoro method cycle:** 4 × (25min work + 5min short break) → 15min long break → cycle reset; bot drives all transitions autonomously with spoken announcements; no manual command required after session start
- **≤ 5 new tool calls:** First target is `tell_joke` (2 files, pure LLM, no oracle); subsequent tools limited to the 5-tool ceiling
- **`project-context.md` updated** to reflect architectural rules established in Phase 1

### Phase 3 — Vision (North Star)

- **Streaming pipeline:** LLM token emission begins → TTS synthesises first sentence while model continues generating; enabled by Protocol-defined boundaries from Phase 1
- **Rolling latency display in web UI:** `PipelineMetrics` sink registered to UI component; live utterance latency visible in browser
- **Swappable model backends:** `mlx`, `onnxruntime` as alternatives to llama-cpp-python, switchable without touching orchestration

### Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Performance gate not met at Q4_K_M | Medium | Blocks Phase 2 | Model sweep tooling provides mechanical comparison; Q5_K_M and thread-count tuning as measured fallback |
| Contracts refactor breaks existing tests | Medium | Delays Phase 1 | Incremental migration; test suite enforced on every commit; no big-bang refactor |
| Pipeline order constraint limits streaming design | Low | Constrains north star | Sequential order preserved; streaming implemented within inter-stage handoff points only |
| Porcupine `.pv` file version mismatch | Low | Breaks wake-word silently | pvporcupine version pinned in `pyproject.toml`; mismatch surfaced in structured startup log |
| Solo dev scope creep into Phase 2 early | Low | Delays Phase 1 | Phase gate is a hard stop; all three AND conditions verified before Phase 2 begins |
| Underestimated refactor depth | Low | Delays Phase 1 | Pre-production = no migration cost; full structural freedom means worst case is a clean rewrite |

## Innovation & Novel Patterns

### Innovation Areas

#### Innovation Area 1: Fully Local Conversational AI on Commodity ARM Hardware

The complete voice assistant pipeline — wake-word detection, speech transcription, LLM inference, TTS synthesis — runs on a Raspberry Pi 5 (ARM Cortex-A76, 8 GB RAM) without cloud calls in the voice path. This is not a stripped-down assistant: real LLM inference (Qwen3 1.7B Q4_K_M via llama-cpp-python), real speech recognition (faster-whisper base), real neural TTS (Piper). German-language wake-word, German-language TTS, local calendar context — integration breadth and local completeness distinguish it from cloud-offloading alternatives. No comparable open-source equivalent exists at this integration level.

#### Innovation Area 2: Streaming LLM → TTS on Edge Hardware (North Star)

The current pipeline buffers each stage to completion before handing downstream — the user waits for the entire LLM response before synthesis begins. The streaming north star: TTS synthesis begins on the first LLM sentence while the model continues generating. On constrained hardware where a full response takes 8–15 seconds of inference time, this collapses "wait and receive" into a genuinely conversational interaction model. The latency improvement is not incremental — it changes the perceived interaction quality category.

#### Innovation Area 3: Architecture-First Streaming Preparation

Rather than retrofitting streaming onto the current architecture, Phase 1 establishes the structural conditions that make streaming tractable: Protocol-defined boundaries between every pipeline stage, first-class IPC envelope types, composable worker interfaces independently testable in isolation. The Phase 1 architectural work is a direct prerequisite for the streaming north star — not generic quality uplift, but targeted preparation for a specific, high-value capability.

### Validation Approach

| Innovation | Validation Method | Success Signal |
|------------|-------------------|----------------|
| Local ML completeness | End-to-end utterance cycle with no network calls | All stages complete offline; no cloud key required for voice pipeline |
| Edge performance | Pi 5 benchmark: throughput + latency sweep | ≥ 10 tok/s; ≤ 25s e2e across 3 representative utterances |
| Streaming readiness | Protocol boundary coverage | All stage interfaces Protocol-backed; composable in unit tests without spawning processes |
| Tool extensibility | Add `tell_joke` post-Phase-1 | ≤ 2 files changed; passes full test suite on first run |

## IoT/Embedded Specific Requirements

### Platform Overview

pomodoro-bot is an always-on embedded voice assistant daemon running on Raspberry Pi 5 (ARM Cortex-A76, 8 GB RAM, Debian Bookworm 64-bit). The device is mains-powered and physically co-located with the user. The complete ML inference pipeline runs on-device — no cloud calls in the voice path. The binary is a single PyInstaller arm64 artefact distributed via GitHub Releases and deployed manually.

### Hardware Requirements

| Requirement | Specification |
|-------------|---------------|
| **Target SoC** | Broadcom BCM2712 (ARM Cortex-A76 quad-core @ 2.4 GHz) |
| **Minimum RAM** | 4 GB (8 GB recommended for model headroom) |
| **Storage** | ≥ 4 GB free for models + binary |
| **Audio I/O** | USB or I²S microphone; ALSA-compatible audio output |
| **Optional I²C** | ENS160 (air quality), ADS1115 + TEMT6000 (ambient light) |
| **Power** | Mains-powered always-on; no battery or power budget constraint |

### CPU Core Assignment

The four ARM Cortex-A76 cores are partitioned to eliminate inter-worker contention:

| Core | Worker | Config Key |
|------|--------|------------|
| 0 | STT (faster-whisper) | `[stt] cpu_cores = [0]` |
| 1–2 | LLM (llama-cpp-python) | `[llm] cpu_cores = [1, 2]` |
| 3 | TTS (piper) | `[tts] cpu_cores = [3]` |

Workers are spawn-isolated subprocesses; affinity is set via `os.sched_setaffinity` at worker startup.

### Connectivity Profile

| Channel | Protocol | Scope |
|---------|----------|-------|
| Voice pipeline | None — fully local | No network required |
| Web UI | WebSocket (ws://localhost:8765) | LAN only |
| Google Calendar (optional) | HTTPS / service account | Outbound only; pipeline not blocked if unavailable |
| Firmware updates | Manual download from GitHub Releases | No automatic update mechanism |

The voice pipeline has zero network dependency. Loss of internet connectivity does not affect core functionality.

### Power Profile

The device runs at full CPU load during active inference. The `performance` CPU governor is required to avoid frequency-scaling latency spikes during LLM inference — applied via `./scripts/pi5_cpu_tuning.sh apply`. The `ondemand` governor (Raspberry Pi OS default) causes measurable latency spikes and must not be used in production.

### Security Model

| Asset | Storage | Access |
|-------|---------|--------|
| `PICO_VOICE_ACCESS_KEY` | `.env` file, not committed | Loaded via `source .env` or `EnvironmentFile=` in systemd unit |
| Google service account JSON | Absolute path in `.env` | Read at startup; never embedded in binary |
| No remote management surface | — | Pi is physically secured; no network-exposed management interface |

Security scope is local-physical. No credential rotation mechanism is in scope for Phase 1 or Phase 2.

### Update Mechanism

Releases are produced by GitHub Actions CI on `git push --tags v*`. Deployment is manual:

1. Download `archive-arm64.tar.gz` from GitHub Releases
2. Extract; replace existing `main` binary
3. Restart: `sudo systemctl restart pomodoro-bot`

No scripted update helper or OTA push mechanism is in scope.

### Build & Deployment Notes

- **Build reproducibility:** `CMAKE_ARGS=-DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8-a` prevents QEMU from enabling dotprod instructions not available on all Pi 5 silicon revisions
- **Native performance rebuild:** `./scripts/pi5_build_optimized_inference.sh` rebuilds llama.cpp on-device with OpenBLAS + OpenMP for throughput beyond the generic binary; run once post-deploy
- **Model placement:** Models are not bundled in the binary; placed manually at paths declared in `config.toml`
- **ALSA device selection:** If multiple audio devices are present, the correct device must be configured in `config.toml`; the audio diagnostic tool assists with selection and VAD threshold tuning

## Functional Requirements

> **Capability contract:** Every feature in this product traces to a requirement below. Capabilities not listed here are out of scope for implementation.

### Voice Interaction Pipeline

- **FR1:** The system can detect a predefined wake word from ambient audio to initiate an interaction cycle
- **FR2:** The system can transcribe a spoken German-language utterance to text
- **FR3:** The system can generate a contextually appropriate text response given a transcribed utterance
- **FR4:** The system can synthesise a text response into spoken German-language audio
- **FR5:** The system can execute the complete interaction cycle (wake-word → STT → LLM → TTS) sequentially without user intervention between stages
- **FR6:** The system can route deterministic utterances directly to a handler without LLM inference

### Pomodoro Session Management

- **FR7:** The user can start a Pomodoro work session via voice command
- **FR8:** The user can stop an active Pomodoro session via voice command
- **FR9:** The user can query the current session status and elapsed time via voice command
- **FR10:** The system can autonomously transition from a work phase to a short break after the configured work duration expires
- **FR11:** The system can autonomously transition from a short break back to a work phase after the configured break duration expires
- **FR12:** The system can autonomously trigger a long break after four consecutive work sessions complete
- **FR13:** The system can autonomously reset the Pomodoro cycle to its initial state after a long break completes
- **FR14:** The system can announce each phase transition with a spoken notification without a user command
- **FR15:** The web UI can reflect the current Pomodoro phase and session count in real time

### Tool Dispatch & Execution

- **FR16:** The system can route a recognised intent to the appropriate tool handler based on the tool name
- **FR17:** The system can execute a tool that produces a response using only LLM inference (no external dependency)
- **FR18:** The system can execute a tool that queries the optional calendar oracle for context
- **FR19:** The system can execute a tool that queries optional I²C sensor data for context
- **FR20:** The system can operate correctly when optional oracle integrations are unavailable or disabled

### Performance Observability

- **FR21:** The system can emit per-utterance structured metrics including per-stage latency (STT, LLM, TTS) and LLM token throughput
- **FR22:** The system can emit per-utterance metrics as structured log output in a machine-readable format
- **FR23:** The system can surface worker errors in the same structured output stream as pipeline metrics
- **FR24:** A developer can run a throughput benchmark across LLM model variants and thread configurations on target hardware

### Developer Extensibility

- **FR25:** A developer can register a new tool by modifying the tool contract registry and the dispatch handler
- **FR26:** A developer can locate all external dependency interface definitions in a single canonical namespace
- **FR27:** A developer can run the complete test suite without physical audio hardware, wake-word models, or ML models
- **FR28:** A developer can configure CPU core assignments for each ML worker independently via config file
- **FR29:** A developer can override the default config file path at runtime via environment variable

### Calendar & Sensor Context (Oracle)

- **FR30:** The system can optionally retrieve upcoming calendar events to enrich the LLM context for a given utterance
- **FR31:** The system can optionally retrieve air quality sensor readings to enrich the LLM context
- **FR32:** The system can optionally retrieve ambient light level readings to enrich the LLM context

### Web UI & Visibility

- **FR33:** The user can observe the current assistant state via a browser-based interface
- **FR34:** The web UI can be served over WebSocket to any browser on the local network
- **FR35:** The user can select between available web UI themes

### System Configuration & Operation

- **FR36:** An operator can configure all required pipeline parameters (model paths, wake-word files, CPU assignments) in a single configuration file
- **FR37:** An operator can run the assistant as a persistent background system service
- **FR38:** An operator can diagnose audio input quality and VAD sensitivity using an included diagnostic utility
- **FR39:** An operator can apply CPU performance governor settings for optimal inference throughput using an included script

## Non-Functional Requirements

### Performance

- **NFR-P1:** LLM throughput must be ≥ 10 tokens/second on Raspberry Pi 5 under representative conversational load, measured using the included model sweep benchmark
- **NFR-P2:** End-to-end latency (wake-word detection → first spoken word of response) must be ≤ 25 seconds, measured across a minimum of 3 representative utterances
- **NFR-P3:** `PipelineMetrics` must be emitted synchronously with each completed utterance cycle — no buffering or batch aggregation

### Reliability

- **NFR-R1:** A crash or exception in any ML worker subprocess (STT, LLM, TTS) must not terminate the main process; the failure must be logged in the structured output stream and the system must remain in a recoverable state
- **NFR-R2:** Unavailability or misconfiguration of any optional oracle integration (calendar, air quality, ambient light) must not prevent the voice pipeline from completing an interaction
- **NFR-R3:** The system must complete the full Pomodoro cycle autonomously (all four work sessions, short breaks, long break, cycle reset) without requiring operator intervention or manual commands after session start

### Maintainability

- **NFR-M1:** Adding a new tool call that requires no external oracle dependency must require changes to at most 2 source files; a tool with an external dependency must require at most 3 source files
- **NFR-M2:** All external dependency interface definitions must reside in a single canonical namespace such that a developer unfamiliar with the codebase can locate the correct interface definition without tracing import chains
- **NFR-M3:** The composition root (`main.py`) must be the sole location where ML worker instances are constructed and wired together; no hidden instantiation may occur within subordinate modules

### Testability

- **NFR-T1:** The complete test suite must pass without physical audio hardware, ML model files, wake-word model files, or network access
- **NFR-T2:** Each ML worker's public interface must be exercisable in tests without spawning a real subprocess or loading a real model
- **NFR-T3:** `PipelineMetrics` emission must be verifiable via unit test without executing an end-to-end utterance cycle

### Deployment

- **NFR-D1:** The system must be distributable as a single self-contained arm64 binary that includes all Python dependencies and does not require a pre-installed Python runtime on the target device
- **NFR-D2:** All required runtime configuration (model paths, wake-word files, CPU assignments) must be fully expressible in a single TOML configuration file with no required command-line arguments at startup

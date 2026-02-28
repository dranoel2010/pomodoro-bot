# Architecture — Pomodoro Bot

> **Scan level:** Quick (pattern-based)
> **Generated:** 2026-02-28

## Executive Summary

Pomodoro Bot is a **local-first voice assistant** running as a Python daemon on Raspberry Pi 5 (ARM64). It lets users control Pomodoro focus sessions, countdown timers, and calendar queries entirely hands-free. All ML inference (wake-word, transcription, LLM, TTS) runs locally — no cloud calls in the voice pipeline.

The architecture is built around three design pillars:

1. **Spawn-isolated process workers** — every CPU-intensive task (STT, LLM, TTS) runs in its own `multiprocessing.Process` using the `spawn` context, preventing shared-memory corruption and enabling CPU core pinning on the Pi 5's 4-core ARM Cortex-A76.
2. **Event-queue driven engine** — the `RuntimeEngine` owns a single `asyncio` queue; all writes go through `QueueEventPublisher` to prevent unsynchronised state mutations.
3. **Protocol-based contracts** — `STTClient`, `LLMClient`, `TTSClient` are Python `Protocol` definitions; the engine only touches these interfaces, making all three components swappable and independently testable.

## Technology Stack

| Category | Technology | Version | Notes |
|----------|-----------|---------|-------|
| Language | Python | ≥ 3.13 | Uses `tomllib` (stdlib), TypedDict, frozen dataclasses |
| Package manager | uv | latest | `[tool.uv] package = false` — not installed as a package |
| LLM inference | llama-cpp-python | ≥ 0.3.16 | Local GGUF models, GBNF grammar-constrained JSON output |
| LLM model | Qwen3-1.7B-Q4_K_M | — | Recommended for Pi 5 — ~7 tok/s at 4 threads |
| STT | faster-whisper | ≥ 1.2.1 | `int8` compute_type on CPU, `vad_filter=True` in production |
| Wake-word | pvporcupine + pvrecorder | proprietary | ARM64 binaries — version must match `.pv` / `.ppn` files exactly |
| TTS | piper-tts | — | Thorsten-VITS German voice; sounddevice for playback |
| Audio output | sounddevice | ≥ 0.5.5 | PortAudio backend |
| Oracle (calendar) | google-api-python-client | ≥ 2.0 | Optional; activated via config flag |
| Oracle (sensors) | adafruit-circuitpython-ens160 | ≥ 1.0.8 | Optional; ENS160 air quality sensor via I²C |
| Web UI server | websockets | ≥ 15.0.1 | WebSocket broadcaster + aiohttp-style static serving |
| ML utilities | huggingface-hub | ≥ 0.36.2 | Model downloads; `transformers < 5` hard ceiling |
| Process monitoring | psutil | ≥ 7.2.2 | CPU affinity, core pinning |
| Build/distribution | PyInstaller | latest | One-file arm64 binary for Pi releases |
| CI/CD | GitHub Actions | — | arm64 Docker (QEMU) build on tag push |

## Architecture Pattern

**Event-driven service daemon with spawn-isolated ML workers.**

```
┌─────────────────────────────────────────────────────────────┐
│                      Main Process (asyncio)                  │
│                                                             │
│  ┌──────────────┐   events    ┌─────────────────────────┐  │
│  │ RuntimeEngine│◄────────────│  QueueEventPublisher     │  │
│  │   (event     │             └─────────────────────────┘  │
│  │    loop)     │                         ▲                  │
│  └──────┬───────┘                         │                  │
│         │ dispatches                      │                  │
│         ▼                                 │                  │
│  ┌──────────────┐    ┌────────────────────┴──────────────┐  │
│  │ utterance.py │    │ ticks.py (periodic timer checks)   │  │
│  │  pipeline    │    └───────────────────────────────────┘  │
│  └──────┬───────┘                                           │
│         │ calls via Protocol                                 │
│         ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              RuntimeComponents (DI container)        │    │
│  │  stt_client  llm_client  tts_client  oracle  pomodoro│    │
│  └───────┬──────────┬───────────┬───────────────────────┘   │
│          │          │           │                            │
└──────────┼──────────┼───────────┼────────────────────────────┘
           │ IPC      │ IPC       │ IPC  (multiprocessing queues)
  ┌────────▼───┐ ┌────▼───────┐ ┌▼───────────┐
  │ STTWorker  │ │ LLMWorker  │ │ TTSWorker  │
  │  (Process) │ │  (Process) │ │  (Process) │
  │            │ │            │ │            │
  │ pvporcupine│ │llama-cpp   │ │ piper-tts  │
  │ pvrecorder │ │ GBNF JSON  │ │sounddevice │
  │faster-whis.│ │fast-path   │ │            │
  └────────────┘ └────────────┘ └────────────┘
```

## Data Architecture

No persistent database. State is entirely in-memory:

| State | Owner | Type |
|-------|-------|------|
| Pomodoro phase + time | `PomodoroTimer` (main process) | Dataclass, frozen per tick |
| Countdown timer | Separate `asyncio` timer handle in engine | Independent of PomodoroTimer |
| LLM context window | `LLMWorker` process (global `_process_instance`) | In-process memory |
| STT model | `STTWorker` process | In-process memory |
| TTS model | `TTSWorker` process | In-process memory |
| Oracle context | `OracleContextService` (main process, cached) | Dict refreshed per utterance |
| Active WebSocket clients | `UIServer` (main process) | Set of connections |

## Component Overview

### `_ProcessWorker` (runtime/workers/core.py)

The foundation of all ML workers. Manages:
- Process lifecycle (start, auto-restart on crash)
- Typed `_RequestEnvelope` / `_ResponseEnvelope` IPC
- `WorkerError` hierarchy (`WorkerInitError`, `WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError`)
- CPU affinity assignment via `psutil`

**Rule:** All new ML workers must compose `_ProcessWorker` — never subclass without it.

### Fast-path Router (llm/fast_path.py)

Before calling the LLM, `utterance.py` checks if the transcribed text matches a deterministic pattern (e.g. "Pomodoro starten", "Timer auf 5 Minuten"). If matched, the tool call is synthesised directly — no LLM inference. Controlled by `llm.fast_path_enabled` in config.

### GBNF Grammar (llm/)

`llama-cpp-python` is given a GBNF grammar at inference time that constrains output to valid JSON matching the `StructuredResponse` schema. `TOOLS_WITHOUT_ARGUMENTS` in `contracts/tool_contract.py` controls which tools appear without an argument field in the grammar.

### Oracle Module (oracle/)

Optional context injection into the LLM system prompt:
- **Google Calendar** — upcoming events from a service account
- **ENS160 sensor** — air quality (CO₂ / TVOC) via I²C (Raspberry Pi only)
- **ADS1115/TEMT6000** — ambient light via ADC (Raspberry Pi only)

Oracle is disabled when `oracle.enabled = false` in `config.toml`.

### UI Server (server/)

Lightweight WebSocket + HTTP server (no framework). Browser UIs (`jarvis/` and `miro/`) connect via WebSocket and receive state push events (timer updates, utterance events, tool results). The UI variant is selected via `ui_server.ui` in config.

## API Design

No external REST API. The WebSocket server (`src/server/ui_server.py`) exposes:
- **Push events** → sent to all connected clients on state changes
- **Event types** defined in `src/contracts/ui_protocol.py` and `src/server/events.py`

## Testing Strategy

| Layer | Approach |
|-------|---------|
| Unit | Pure Python; native extensions (pvporcupine, llama-cpp-python, piper-tts) stubbed via `sys.modules` injection before import |
| Integration | `_ProcessWorker` patched in worker factory tests; real `multiprocessing` queues used |
| Contract guards | Source-text scanning tests (`test_contract_guards.py`) enforce architectural invariants at the code level |
| Characterisation | Parser and timer tests lock current behaviour to detect regressions |

**Test discovery:** `uv run pytest tests/` — all tests must pass before any commit.

## Deployment Architecture

### Development (source)

```
setup.sh          # uv sync --frozen (installs from uv.lock)
source .env        # load secrets
uv run python src/main.py
```

### Release (Raspberry Pi binary)

PyInstaller bundles the entire Python environment + source into a single executable (`dist/main`). The CI pipeline builds the arm64 binary using Docker QEMU emulation on `ubuntu-latest`, then uploads to GitHub Releases.

```
build.sh           # PyInstaller --onefile → dist/main + dist/archive.tar.gz
dist/main          # Self-contained arm64 executable
dist/config.toml   # Default config shipped with release
dist/.env          # Secrets template shipped with release
```

**CI trigger:** `git push --tags v*` → GitHub Actions workflow (`release.yml`)

### Raspberry Pi 5 Performance Tuning

- CPU governor: performance mode (`pi5_cpu_tuning.sh apply`)
- llama.cpp: native ARM64 build with OpenBLAS + OpenMP (`pi5_build_optimized_inference.sh`)
- CPU pinning: STT/LLM/TTS each pinned to dedicated cores via `stt.cpu_cores`, `llm.cpu_cores`, `tts.cpu_cores` in `config.toml`

## Critical Constraints

> See `_bmad-output/project-context.md` for the full set of 47+ implementation rules.

| Constraint | Reason |
|-----------|--------|
| `multiprocessing` spawn context only — never `fork` | pvporcupine and llama-cpp-python are not fork-safe |
| `ThreadPoolExecutor(max_workers=1)` in engine is intentional | Prevents concurrent utterance processing |
| `QueueEventPublisher` is the only write path into the engine queue | Preserves event serialisation invariant |
| `TOOL_NAME_ORDER` in `contracts/tool_contract.py` is the single source of truth | Grammar generation and dispatch depend on order consistency |
| `transformers < 5` hard ceiling in pyproject.toml | faster-whisper depends on tokenizer internals that changed in v5 |
| llama-cpp-python version pin requires GBNF API verification | GBNF API changed across minor versions — do not bump without testing |
| pvporcupine `.pv` and `.ppn` files must match the installed package version exactly | Binary compatibility enforced at load time |
| `vad_filter=True` in STT production config | Reduces hallucinations on silence; never disable in production |

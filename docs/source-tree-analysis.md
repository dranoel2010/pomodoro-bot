# Source Tree Analysis — Pomodoro Bot

> **Scan level:** Quick (pattern-based)
> **Generated:** 2026-02-28

## Repository Layout

```
pomodoro-bot/                       # Project root (monolith)
│
├── src/                            # [SOURCE ROOT] All Python packages
│   ├── main.py                     # [ENTRY POINT] App startup + composition root
│   ├── app_config.py               # Config loader (TOML + env vars, PyInstaller-aware)
│   ├── app_config_parser.py        # TOML section parsing + validation
│   ├── app_config_schema.py        # Config dataclass schema definitions
│   │
│   ├── contracts/                  # Shared protocol constants
│   │   ├── tool_contract.py        # [KEY] TOOL_NAME_ORDER — single source of truth for all tool names
│   │   └── ui_protocol.py          # WebSocket event type constants
│   │
│   ├── runtime/                    # [CORE] Main orchestration engine
│   │   ├── engine.py               # RuntimeEngine event loop + RuntimeComponents DI container
│   │   ├── contracts.py            # STTClient, LLMClient, TTSClient Protocol definitions
│   │   ├── utterance.py            # Utterance pipeline: STT → fast-path → LLM → tool dispatch → TTS
│   │   ├── ticks.py                # Periodic tick scheduler (timer/pomodoro monitoring)
│   │   ├── ui.py                   # UI server push integration (QueueEventPublisher)
│   │   ├── workers/
│   │   │   ├── core.py             # [KEY] _ProcessWorker base class + WorkerError hierarchy
│   │   │   ├── llm.py              # LLMWorker: llama-cpp-python in spawned process
│   │   │   ├── stt.py              # STTWorker: faster-whisper in spawned process
│   │   │   └── tts.py              # TTSWorker: piper-tts + sounddevice in spawned process
│   │   └── tools/
│   │       ├── dispatch.py         # Tool name → handler routing table
│   │       ├── calendar.py         # Calendar tool handlers (Google Calendar via oracle)
│   │       └── messages.py         # Timer/pomodoro response message builders
│   │
│   ├── llm/                        # LLM module
│   │   ├── service.py              # LLMService: system prompt loading + inference
│   │   ├── fast_path.py            # Deterministic command bypass (no LLM call)
│   │   ├── parser.py               # Structured JSON response parser
│   │   ├── parser_extractors.py    # JSON field extraction helpers
│   │   ├── parser_messages.py      # Parser-level response messages
│   │   ├── parser_rules.py         # Parser validation rules
│   │   ├── factory.py              # LLMWorker factory
│   │   ├── config.py               # LLM config dataclass
│   │   ├── types.py                # StructuredResponse, ToolCall, EnvironmentContext TypeDicts
│   │   ├── llama_backend.py        # llama-cpp-python backend wrapper
│   │   └── model_store.py          # Model path resolution + symlink management
│   │
│   ├── stt/                        # Speech-to-text module
│   │   ├── service.py              # faster-whisper transcription service
│   │   ├── capture.py              # Audio capture via pvrecorder
│   │   ├── stt.py                  # STT pipeline integration
│   │   ├── vad.py                  # Voice activity detection (silence trimming)
│   │   ├── events.py               # STT event types (WakeWordDetected, UtteranceCaptured)
│   │   ├── factory.py              # STTWorker factory
│   │   └── config.py               # STT config dataclass
│   │
│   ├── tts/                        # Text-to-speech module
│   │   ├── service.py              # TTS generation service
│   │   ├── engine.py               # piper-tts model loading + synthesis
│   │   ├── output.py               # sounddevice audio playback
│   │   ├── factory.py              # TTSWorker factory
│   │   └── config.py               # TTS config dataclass
│   │
│   ├── oracle/                     # Optional environment context module
│   │   ├── service.py              # OracleContextService: aggregates provider data
│   │   ├── providers.py            # Context provider protocol + registry
│   │   ├── contracts.py            # Oracle Protocol definitions
│   │   ├── factory.py              # Oracle factory
│   │   ├── config.py               # Oracle config dataclass
│   │   ├── errors.py               # Oracle-specific error types
│   │   ├── calendar/               # Google Calendar integration
│   │   └── sensor/                 # Hardware sensor readers (ENS160, ADS1115/TEMT6000)
│   │
│   ├── pomodoro/                   # Pomodoro timer state machine module
│   │   ├── service.py              # PomodoroTimer: phase tracking state machine
│   │   ├── constants.py            # Timer durations (work/short-break/long-break)
│   │   └── tool_mapping.py         # Pomodoro tool name → timer action mapping
│   │
│   ├── server/                     # UI server module
│   │   ├── ui_server.py            # WebSocket broadcaster + HTTP static file server
│   │   ├── service.py              # Server lifecycle management
│   │   ├── events.py               # Server-side event type definitions
│   │   ├── static_files.py         # Static file resolution (PyInstaller-aware)
│   │   ├── factory.py              # Server factory
│   │   └── config.py               # Server config dataclass
│   │
│   ├── shared/                     # Shared constants module
│   │   ├── defaults.py             # Default configuration values
│   │   └── env_keys.py             # Environment variable key name constants
│   │
│   └── debug/                      # Developer diagnostic utilities
│       ├── audio_diagnostic.py     # Interactive VAD tuning tool (pvrecorder)
│       └── prompt_benchmark.py     # LLM throughput benchmarking script
│
├── tests/                          # Automated test suite (pytest)
│   ├── runtime/                    # Runtime + worker tests
│   │   ├── test_contract_guards.py     # Source-text scanning safety tests
│   │   ├── test_utterance_state_flow.py
│   │   ├── test_worker_context_manager.py
│   │   ├── test_llm_worker_factory.py
│   │   ├── test_stt_worker_factory.py
│   │   ├── test_tts_worker_factory.py
│   │   ├── test_process_workers_recovery.py
│   │   ├── test_tool_dispatch.py
│   │   ├── test_calendar_tools.py
│   │   ├── test_ticks_state_flow.py
│   │   ├── test_tool_contract_consistency.py
│   │   └── test_tool_mapping_safety.py
│   ├── llm/                        # LLM service, parser, fast-path tests
│   ├── stt/                        # STT factory + config tests
│   ├── tts/                        # TTS factory + config tests
│   ├── oracle/                     # Oracle provider + sensor tests
│   ├── pomodoro/                   # Pomodoro state machine tests
│   ├── server/                     # Server factory + config tests
│   ├── config/                     # App config loading tests
│   └── test_main_startup.py        # Smoke test for main entrypoint
│
├── web_ui/                         # Browser UIs (served statically by src/server)
│   ├── jarvis/                     # Dark "JARVIS" voice assistant UI
│   │   ├── index.html
│   │   ├── app.js                  # WebSocket client + UI state
│   │   └── styles.css
│   └── miro/                       # Light "Miro" minimal UI
│       ├── index.html
│       ├── app.js
│       └── styles.css
│
├── prompts/                        # LLM system prompt templates
│   ├── system_prompt.md            # Current active prompt (symlinked by service)
│   ├── system_prompt_v2.md – v6.md # Historical prompt evolution
│   └── (v6 = current)
│
├── models/                         # ML model storage (content gitignored)
│   ├── llm/                        # GGUF LLM models (Qwen3-1.7B-Q4_K_M recommended)
│   │   ├── qwen/
│   │   ├── qwen3/
│   │   └── alternatives/
│   ├── stt/                        # faster-whisper HuggingFace model cache
│   └── tts/                        # Piper TTS voice models (thorsten-piper)
│
├── scripts/                        # Raspberry Pi 5 optimization scripts
│   ├── pi5_build_optimized_inference.sh  # Native llama.cpp build (OpenBLAS/OpenMP)
│   ├── pi5_cpu_tuning.sh           # CPU governor + thermal status/tuning
│   └── pi5_model_sweep.py          # Model/quantization throughput benchmark
│
├── .github/workflows/
│   └── release.yml                 # CI: arm64 Docker build + GitHub Release on tag push
│
├── config.toml                     # [CONFIG] Runtime configuration (non-secret)
├── .env.dist                       # Secret key template (PICO_VOICE_ACCESS_KEY etc.)
├── .env                            # Local secrets (gitignored)
├── pyproject.toml                  # Project metadata + dependencies (uv)
├── uv.lock                         # Locked dependency versions
├── setup.sh                        # Dev environment bootstrap (uv sync)
├── build.sh                        # PyInstaller one-file build script
└── main.spec                       # PyInstaller spec (for arm64 packaging)
```

## Critical Directories

| Directory | Purpose |
|-----------|---------|
| `src/runtime/` | Core orchestration engine — event loop, utterance pipeline, worker management |
| `src/runtime/workers/` | Process-isolated CPU workers (STT, LLM, TTS) — composed from `_ProcessWorker` |
| `src/runtime/tools/` | Tool dispatch layer — routes LLM tool calls to handlers |
| `src/contracts/` | Canonical tool name registry — single source of truth for all tool identifiers |
| `src/llm/` | LLM inference pipeline — grammar-constrained JSON, fast-path bypass |
| `src/stt/` | Wake-word detection + transcription (pvporcupine + faster-whisper) |
| `src/tts/` | TTS synthesis + audio playback (piper-tts + sounddevice) |
| `src/oracle/` | Optional environment context (calendar, sensors) injected into LLM prompt |
| `src/pomodoro/` | Pomodoro phase tracking state machine |
| `src/server/` | WebSocket broadcaster + HTTP static UI server |
| `tests/runtime/` | Contract guards + integration tests for worker safety properties |
| `models/` | Local model storage (LLM/STT/TTS — populated at runtime, not in git) |
| `prompts/` | LLM system prompt versions |
| `scripts/` | Raspberry Pi 5 performance optimization tools |

## Integration Points

```
main.py
  └── builds RuntimeComponents (STTWorker, LLMWorker, TTSWorker, oracle, pomodoro, ui_server)
       └── hands to RuntimeEngine
            ├── WakeWordDetectedEvent → start utterance capture
            ├── UtteranceCapturedEvent → utterance.py pipeline
            │    ├── STTWorker.transcribe()
            │    ├── fast_path check (deterministic bypass)
            │    ├── LLMWorker.complete() [if needed]
            │    ├── tools/dispatch.py → tool handlers
            │    └── TTSWorker.speak()
            ├── ticks.py → periodic timer monitoring
            └── ui.py → WebSocket push to browser (server/)
```

# Development Guide — Pomodoro Bot

> **Generated:** 2026-02-28

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | ≥ 3.11 (3.13 recommended) | `pyproject.toml` requires `>=3.13` |
| uv | latest | Package manager — replaces pip/venv |
| PortAudio | system library | Required for sounddevice audio I/O |
| microphone | any | Physical audio input device |
| Picovoice access key | — | Free tier available at console.picovoice.ai |
| Wake-word model | `.ppn` file | Generated for your custom keyword |
| Porcupine params | `.pv` file | Matched to pvporcupine version — CRITICAL |

### Optional Prerequisites

| Requirement | Purpose |
|-------------|---------|
| Google service account JSON | Google Calendar integration |
| ENS160 sensor (I²C) | Air quality context (Raspberry Pi only) |
| ADS1115 + TEMT6000 (I²C) | Ambient light context (Raspberry Pi only) |
| `rpi-lgpio` package | RPi.GPIO compatibility on Pi 5 — do NOT install alongside `RPi.GPIO` |

## Platform Setup

### macOS (Development)

```bash
brew install uv python@3.11 portaudio git
git clone https://github.com/dranoel2010/pomodoro-bot.git
cd pomodoro-bot
./setup.sh
source .venv/bin/activate
```

### Raspberry Pi OS 64-bit Bookworm (Production Target)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl git libasound2-dev
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

git clone https://github.com/dranoel2010/pomodoro-bot.git
cd pomodoro-bot
./setup.sh
source .venv/bin/activate
```

## Environment Setup

```bash
# 1. Install dependencies (reads uv.lock for reproducible builds)
./setup.sh

# 2. Create your .env file from the template
cp .env.dist .env

# 3. Edit .env — set required secrets:
#    PICO_VOICE_ACCESS_KEY="your-key-from-console.picovoice.ai"
#
# Optional secrets:
#    HF_TOKEN="..."                          # Hugging Face token (for private models)
#    ORACLE_GOOGLE_CALENDAR_ID="primary"     # Google Calendar integration
#    ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service-account.json"
#
# Optional config override:
#    APP_CONFIG_FILE="/absolute/path/to/config.toml"

# 4. Edit config.toml — set required paths:
#    [wake_word]
#    ppn_file = "models/sst/hey-pomo.ppn"   # your .ppn file
#    pv_file = "models/sst/porcupine_params_de.pv"  # must match pvporcupine version
```

### Key config.toml Sections

```toml
[wake_word]
ppn_file = "models/sst/hey-pomo.ppn"     # REQUIRED: path to wake-word model
pv_file = "models/sst/porcupine_params_de.pv"  # REQUIRED: must match pvporcupine version

[stt]
model_size = "base"       # base | small | medium
compute_type = "int8"     # int8 (CPU default) — must change device if you change this
cpu_threads = 2
beam_size = 1
vad_filter = true         # NEVER disable in production

[llm]
model_path = "models/llm/qwen3/Qwen3-1.7B-Q4_K_M.gguf"
fast_path_enabled = true  # deterministic command bypass
n_threads = 4
n_ctx = 2048
max_tokens = 128

[tts]
model_path = "models/tts/thorsten-piper"
voice = "thorsten"

[ui_server]
ui = "jarvis"             # jarvis | miro
host = "0.0.0.0"
port = 8765

[oracle]
enabled = false           # set true to enable calendar/sensor context
```

## Local Development Commands

```bash
# Activate virtualenv (if not using `uv run` prefix)
source .venv/bin/activate

# Load secrets
source .env

# Run the application
uv run python src/main.py

# Run with a custom config
APP_CONFIG_FILE="/path/to/custom-config.toml" uv run python src/main.py

# Run diagnostics (VAD tuning)
uv run python src/debug/audio_diagnostic.py

# Run LLM throughput benchmark (Pi 5)
UV_CACHE_DIR=.uv-cache uv run python scripts/pi5_model_sweep.py \
  --models models/llm/qwen3/Qwen3-1.7B-Q4_K_M.gguf \
  --threads 2,3,4 \
  --runs 3 \
  --json-out /tmp/pi5-llm-benchmark.json
```

## Testing

```bash
# Run all tests
uv run pytest tests/

# Run a specific module's tests
uv run pytest tests/runtime/
uv run pytest tests/llm/
uv run pytest tests/stt/

# Run with verbose output
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/runtime/test_utterance_state_flow.py
```

### Testing Conventions

- All native dependencies (`pvporcupine`, `llama-cpp-python`, `piper-tts`, `pvrecorder`, `sounddevice`) are stubbed via `sys.modules` injection before import — tests never require hardware
- `_ProcessWorker` is patched in worker factory tests — no actual subprocesses started
- Tests use hand-written stub classes (e.g. `_UIServerStub`) not `MagicMock` for complex protocols
- Runtime package is manually registered in `sys.modules` for tests that import internal modules

### Test Invariants (enforced by `test_contract_guards.py`)

- Worker modules must NOT contain `global _*` patterns (except the explicit `_process_instance` in `llm/workers/llm.py`)
- Runtime signature files must NOT use `dict[str, object]` — use typed dataclasses or TypedDicts

## Build Process

```bash
# Build one-file PyInstaller binary (local, current arch)
./build.sh

# Output:
#   dist/main          — executable
#   dist/config.toml   — default config
#   dist/.env          — secrets template
#   dist/archive.tar.gz — all of the above, compressed

# Run the built binary
source dist/.env    # set your secrets
./dist/main
```

## Raspberry Pi 5 Performance Toolkit

```bash
# Build native llama.cpp with OpenBLAS + OpenMP (run on the Pi)
./scripts/pi5_build_optimized_inference.sh

# CPU governor + thermal status
./scripts/pi5_cpu_tuning.sh status

# Apply performance governor (requires sudo)
sudo ./scripts/pi5_cpu_tuning.sh apply

# Model/quantization throughput benchmark
UV_CACHE_DIR=.uv-cache uv run python scripts/pi5_model_sweep.py \
  --models models/llm/qwen3/Qwen3-1.7B-Q4_K_M.gguf \
           models/llm/qwen3/Qwen3-1.7B-Q8_0.gguf \
  --threads 2,3,4 \
  --runs 3 \
  --json-out /tmp/pi5-llm-benchmark.json
```

## CPU Pinning (Pi 5)

The 4 ARM Cortex-A76 cores can be assigned dedicated roles to minimise context-switching:

```toml
[stt]
cpu_cores = [0]         # core 0 for STT

[llm]
cpu_cores = [1, 2]      # cores 1-2 for LLM
cpu_affinity_mode = "pinned"  # or "shared" to borrow idle cores

[tts]
cpu_cores = [3]         # core 3 for TTS
```

## Model Management

Models are stored in `models/` (not in git — use `.gitkeep` to preserve directories):

```
models/
├── llm/
│   └── qwen3/
│       └── Qwen3-1.7B-Q4_K_M.gguf    # recommended for Pi 5
├── stt/
│   └── (faster-whisper auto-downloads to models/stt/ via HuggingFace)
└── tts/
    └── thorsten-piper/                 # piper-tts German voice model
```

STT models are auto-downloaded by faster-whisper on first run. LLM and TTS models must be placed manually.

## Adding a New Tool

1. Add the tool name to `TOOL_NAME_ORDER` in `src/contracts/tool_contract.py` (order matters for grammar)
2. If the tool takes no arguments, add it to `TOOLS_WITHOUT_ARGUMENTS`
3. Add handler to `src/runtime/tools/dispatch.py`
4. Update system prompt in `prompts/system_prompt.md` to describe the tool
5. Add fast-path rule to `src/llm/fast_path.py` if the tool has deterministic trigger phrases
6. Write tests in `tests/runtime/test_tool_dispatch.py`

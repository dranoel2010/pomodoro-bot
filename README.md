# Pomodoro Bot

`pomodoro-bot` is a local-first voice assistant for focus work and time management.
Its purpose is to let you control timers and pomodoro sessions hands-free, with optional
calendar awareness and spoken responses. Core capabilities include wake-word detection,
speech transcription, structured local LLM tool-calling, TTS playback, and a live web UI.

Current runtime pipeline (Pipecat-only):
- wake-word + utterance capture (Porcupine + local capture)
- transcription (`faster-whisper`)
- optional local LLM response (`llama.cpp` worker)
- tool dispatch (timer/pomodoro/calendar contract)
- optional TTS playback (`piper`)
- built-in UI server (`server`) serving `web_ui/<ui>/index.html` + websocket updates

## Project layout

- `src/main.py`: app entrypoint and dependency bootstrap.
- `src/app_config.py`: Pipecat-only runtime config loading and validation.
- `src/runtime/`: Pipecat runtime orchestration (`src/runtime/pipecat_engine.py`) plus runtime tool/tick/UI adapters.
- `src/stt/`: wake-word capture + transcription foundation. See `src/stt/README.md`.
- `src/llm/`: local LLM config/download/backend/parser/service. See `src/llm/README.md`.
- `src/tts/`: TTS model loading + playback service. See `src/tts/README.md`.
- `src/oracle/`: optional environment context providers (sensors + calendar). See `src/oracle/README.md`.
- `src/pomodoro/`: pomodoro/timer state machines and tool remapping. See `src/pomodoro/README.md`.
- `src/server/`: static UI + websocket server runtime. See `src/server/README.md`.
- `src/contracts/`: canonical tool names and UI protocol constants. See `src/contracts/README.md`.
- `src/shared/`: shared defaults and environment key constants. See `src/shared/README.md`.
- `src/debug/audio_diagnostic.py`: interactive VAD tuning utility (`src/debug/README.md`).
- `web_ui/`: browser UIs (`jarvis/`, `miro/`) served by `src/server` (`web_ui/README.md`).
- `prompts/`: system prompt templates used by the LLM service.
- `tests/`: automated tests by module (`tests/README.md`).
- `config.toml`: non-secret runtime configuration.
- `.env.dist`: template for environment-based secrets.
- `models/`: local model storage directory.
- `setup.sh`: uv-based environment bootstrap.
- `build.sh`, `main.spec`: one-file build setup (PyInstaller).

## Requirements

- Python 3.11+
- `uv`
- microphone input device
- Picovoice assets:
  - access key
  - wake-word model (`.ppn`)
  - Porcupine params (`.pv`)

## Setup

### Run from source

#### Raspberry/Bookworm

Tested target: Raspberry Pi OS 64-bit (Bookworm).

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl git libasound2-dev
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

git clone https://github.com/dranoel2010/pomodoro-bot.git
# or (SSH):
# git clone git@github.com:dranoel2010/pomodoro-bot.git
cd pomodoro-bot
./setup.sh
source .venv/bin/activate
```

#### macOS

```bash
brew install uv python@3.11 portaudio git

git clone https://github.com/dranoel2010/pomodoro-bot.git
# or (SSH):
# git clone git@github.com:dranoel2010/pomodoro-bot.git
cd pomodoro-bot
./setup.sh
source .venv/bin/activate
```

### Run from release

#### Raspberry/Bookworm

```bash
sudo apt update
sudo apt install -y libasound2

mkdir pomodoro-bot
cd pomodoro-bot
# Download and extract the release archive from GitHub Releases.
# Example:
# curl -L -o pomodoro-bot-release.tar.gz https://github.com/dranoel2010/pomodoro-bot/releases/latest/download/pomodoro-bot-release.tar.gz
# (if the asset name differs, download it from https://github.com/dranoel2010/pomodoro-bot/releases)
tar -xzf pomodoro-bot-release.tar.gz
```

### Configure runtime (all install methods)

Configure runtime settings in `config.toml` (non-secret values).

The repo includes a default Pipecat-only `config.toml` with sections for:
- `pipecat.runtime`
- `pipecat.wake.porcupine`
- `pipecat.stt.faster_whisper`
- `pipecat.llm.local_llama`
- `pipecat.tts.piper`
- `pipecat.ui`
- `pipecat.tools.calendar`

UI selection settings:
- `pipecat.ui.ui`: built-in UI variant (`jarvis` or `miro`)

CPU pinning settings:
- `pipecat.stt.faster_whisper.cpu_cores`
- `pipecat.llm.local_llama.cpu_cores`
- `pipecat.tts.piper.cpu_cores`
- `pipecat.llm.local_llama.cpu_affinity_mode`: `pinned` or `shared`
- `pipecat.llm.local_llama.shared_cpu_reserve_cores`
- STT/LLM/TTS worker logs are forwarded to the main process logger output (stdout).

Required first edit in `config.toml`:
- `pipecat.wake.porcupine.ppn_file`
- `pipecat.wake.porcupine.pv_file`

Set only secrets in `.env` (or your shell), for example:

```bash
export PICO_VOICE_ACCESS_KEY="..."
# optional
# export HF_TOKEN="..."
# required only when pipecat.tools.calendar.google_calendar_enabled=true:
# export ORACLE_GOOGLE_CALENDAR_ID="primary"
# export ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE="/absolute/path/to/service-account.json"
```

If you want to use a different config file path:

```bash
export APP_CONFIG_FILE="/absolute/path/to/config.toml"
```

## Run (source checkout)

```bash
source .env
uv run python src/main.py
```

Then open the UI at:

```text
http://127.0.0.1:8765
```

## Run (release download)

```bash
source .env
./main
```

Then open the UI at:

```text
http://127.0.0.1:8765
```

For release archives, run the packaged binary from the extracted release directory.

## Diagnostics

```bash
source .env
uv run python src/debug/audio_diagnostic.py
```

## Raspberry Pi 5 Throughput Toolkit

Native llama.cpp build (OpenBLAS/OpenMP + native CPU flags):

```bash
./scripts/pi5_build_optimized_inference.sh
```

CPU governor and thermal status/tuning:

```bash
./scripts/pi5_cpu_tuning.sh status
sudo ./scripts/pi5_cpu_tuning.sh apply
```

Model/quantization throughput sweep and ranking:

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/pi5_model_sweep.py \
  --models models/llm/qwen/Qwen3-1.7B-Q4_K_M.gguf \
           models/llm/qwen/Qwen3-1.7B-Q8_0.gguf \
  --threads 2,3,4 \
  --runs 3 \
  --json-out /tmp/pi5-llm-benchmark.json
```

## Optional Oracle Dependencies

- Google Calendar: `google-auth`, `google-api-python-client`
- ENS160 sensor: `adafruit-blinka`, `adafruit-circuitpython-ens160`
  - Raspberry Pi 5 note: install `rpi-lgpio` (which provides `RPi.GPIO`
    compatibility) and do not keep `RPi.GPIO` installed in the same virtualenv.
- TEMT6000 via ADS1115: `Adafruit_ADS1x15`

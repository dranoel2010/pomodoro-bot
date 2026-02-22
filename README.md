# Pomodoro Bot

`pomodoro-bot` is a local-first voice assistant for focus work and time management.
Its purpose is to let you control timers and pomodoro sessions hands-free, with optional
calendar awareness and spoken responses. Core capabilities include wake-word detection,
speech transcription, structured local LLM tool-calling, TTS playback, and a live web UI.

Current runtime pipeline:
- wake-word + utterance capture (`stt`)
- transcription (`faster-whisper`)
- optional local LLM response (`llm`)
- optional TTS playback (`tts`)
- built-in UI server (`server`) serving `web_ui/<ui>/index.html` + websocket updates

## Project layout

- `src/main.py`: app entrypoint and dependency bootstrap.
- `src/app_config.py`, `src/app_config_parser.py`, `src/app_config_schema.py`: runtime config loading and validation.
- `src/runtime/`: main orchestration loop (events, utterance pipeline, tool dispatch). See `src/runtime/README.md`.
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

The repo includes a default `config.toml` with sections for:
- `wake_word`
- `stt`
- `tts`
- `llm`
- `ui_server`
- `oracle`

UI selection settings:
- `ui_server.ui`: built-in UI variant (`jarvis` or `miro`)

Required first edit in `config.toml`:
- `wake_word.ppn_file`
- `wake_word.pv_file`

Set only secrets in `.env` (or your shell), for example:

```bash
export PICO_VOICE_ACCESS_KEY="..."
# optional
# export HF_TOKEN="..."
# required only when oracle.google_calendar_enabled=true in config.toml:
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

## Optional Oracle Dependencies

- Google Calendar: `google-auth`, `google-api-python-client`
- ENS160 sensor: `adafruit-blinka`, `adafruit-circuitpython-ens160`
- TEMT6000 via ADS1115: `Adafruit_ADS1x15`

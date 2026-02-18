# pomodoro-bot

Voice-driven pomodoro assistant prototype.

Current runtime pipeline:
- wake-word + utterance capture (`stt`)
- transcription (`faster-whisper`)
- optional local LLM response (`llm`)
- optional TTS playback (`tts`)
- built-in UI server (`server`) serving `web_ui/index.html` + websocket updates

## Project layout

- `src/main.py`: app entrypoint and orchestration.
- `src/stt/`: wake-word capture + STT foundation. See `src/stt/README.md`.
- `src/llm/`: local LLM config/download/backend/parser/service. See `src/llm/README.md`.
- `src/tts/`: TTS model loading + playback service. See `src/tts/README.md`.
- `src/oracle/`: optional environment context providers (sensors + calendar).
- `src/server/`: static UI + websocket server runtime.
- `web_ui/`: browser UI (`index.html`) served by `src/server`.
- `src/audio-diagnostic.py`: VAD tuning utility.
- `setup.sh`: uv-based env bootstrap.
- `build.sh`: one-file build script (PyInstaller).

## Requirements

- Python 3.11+
- `uv`
- microphone input device
- Picovoice assets:
  - access key
  - wake-word model (`.ppn`)
  - Porcupine params (`.pv`)

### Raspberry Pi 5 prerequisites

Tested target: Raspberry Pi OS 64-bit (Bookworm).

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl git libasound2-dev
python3 --version
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
uv --version
```

## Setup

```bash
./setup.sh
```

Configure environment variables (example):

```bash
export PICO_VOICE_ACCESS_KEY="..."
export PORCUPINE_PPN_FILE="/absolute/path/to/hey-pomo.ppn"
export PORCUPINE_PV_FILE="/absolute/path/to/porcupine_params_de.pv"

# STT (optional tuning)
export WHISPER_MODEL_SIZE="small"
export WHISPER_DEVICE="cpu"
export WHISPER_COMPUTE_TYPE="int8"
export WHISPER_LANGUAGE="de"
export WHISPER_BEAM_SIZE="5"
export WHISPER_VAD_FILTER="true"

# TTS (optional)
export TTS_ENABLED="true"
export TTS_MODEL_PATH="models/tts/thorsten_vits/model_file.pth"
export TTS_CONFIG_PATH="models/tts/thorsten_vits/config.json"
# download fallback if files are missing:
# export TTS_HF_REPO_ID="Thorsten-Voice/VITS"
# export TTS_HF_LOCAL_DIR="models/tts/thorsten_vits"
# export TTS_OUTPUT_DEVICE="0"
# export TTS_GPU="false"

# LLM (optional)
# LLM_MODEL_PATH is a directory where LLM_HF_FILENAME is expected.
export LLM_MODEL_PATH="models/llm/qwen2_5"
export LLM_HF_FILENAME="Qwen2.5-3B-Instruct-Q4_K_M.gguf"
# if file is missing, this repo will be used to download it:
export LLM_HF_REPO_ID="Qwen/Qwen2.5-3B-Instruct-GGUF"
# optional:
# export LLM_HF_REVISION="main"
# export HF_TOKEN="..."
# export ENABLE_LLM="true"   # optional explicit switch
# export LLM_SYSTEM_PROMPT="/absolute/path/to/system_prompt.md"

# Oracle integrations (optional environment context for LLM)
# export ORACLE_ENABLED="true"
# export ORACLE_ENS160_ENABLED="false"
# export ORACLE_TEMT6000_ENABLED="false"
# export ORACLE_GOOGLE_CALENDAR_ENABLED="false"
# export ORACLE_GOOGLE_CALENDAR_ID="primary"
# export ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE="/absolute/path/to/service-account.json"
# export ORACLE_GOOGLE_CALENDAR_MAX_RESULTS="5"
# export ORACLE_SENSOR_CACHE_TTL_SECONDS="15"
# export ORACLE_CALENDAR_CACHE_TTL_SECONDS="60"

# UI server (optional; enabled by default)
# export UI_SERVER_ENABLED="true"
# export UI_SERVER_HOST="127.0.0.1"
# export UI_SERVER_PORT="8765"
# export UI_SERVER_WS_PATH="/ws"
# export UI_SERVER_INDEX_FILE="/absolute/path/to/web_ui/index.html"
```

## Run

```bash
source .env
uv run python src/main.py
```

Then open the UI at:

```text
http://127.0.0.1:8765
```

## Diagnostics

```bash
source .env
uv run python src/audio-diagnostic.py
```

## Optional Oracle Dependencies

- Google Calendar: `google-auth`, `google-api-python-client`
- ENS160 sensor: `adafruit-blinka`, `adafruit-circuitpython-ens160`
- TEMT6000 via ADS1115: `Adafruit_ADS1x15`

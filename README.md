# pomodoro-bot

Voice-driven pomodoro assistant prototype.

Current runtime pipeline:
- wake-word + utterance capture (`stt`)
- transcription (`faster-whisper`)
- optional local LLM response (`llm`)
- optional TTS playback (`tts`)

## Project layout

- `src/main.py`: app entrypoint and orchestration.
- `src/stt/`: wake-word capture + STT foundation. See `src/stt/README.md`.
- `src/llm/`: local LLM config/download/backend/parser/service. See `src/llm/README.md`.
- `src/tts/`: TTS model loading + playback service. See `src/tts/README.md`.
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
```

## Run

```bash
source .env
uv run python src/main.py
```

## Diagnostics

```bash
source .env
uv run python src/audio-diagnostic.py
```

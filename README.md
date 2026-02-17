# pomodoro-bot

Voice-driven wake-word + speech-to-text prototype using Picovoice Porcupine and faster-whisper.

## What it does

- Listens continuously for a custom wake word.
- Captures the utterance after wake-word detection.
- Uses VAD (voice activity detection) + silence detection to decide when speech is done.
- Transcribes captured audio with faster-whisper.
- Publishes wake-word and utterance events through a queue-based event interface.

## Project layout

- `src/main.py`: CLI entrypoint, wiring, lifecycle, and event loop.
- `src/wake_word/`: wake-word module (service, events, VAD, capture, STT).
- `src/audio-diagnostic.py`: diagnostic tool for tuning VAD thresholds.
- `setup.sh`: virtualenv bootstrap + dependency install.

## Requirements

- Python 3.11+
- uv (for environment + dependency management)
- Microphone input device
- Picovoice assets:
  - Access key
  - Wake-word model (`.ppn`)
  - Porcupine params file (`.pv`)

### Raspberry Pi 5 prerequisites

Tested target: Raspberry Pi OS 64-bit (Bookworm) on Raspberry Pi 5.

1. Install system packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl git libasound2-dev
```

2. Ensure Python is 3.11+:

```bash
python3 --version
```

3. Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env
uv --version
```

### Raspberry Pi 5 quick start

```bash
# 1) Install system dependencies
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl git libasound2-dev

# 2) Install uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

# 3) Clone and enter the project
git clone <your-repo-url>
cd pomodoro-bot

# 4) Create .venv and install locked dependencies
./setup.sh

# 5) Configure runtime env
# set and export:
# - PICO_VOICE_ACCESS_KEY
# - PORCUPINE_PPN_FILE
# - PORCUPINE_PV_FILE

# 6) Run
uv run python src/main.py
```

## Setup

1. Install uv (one-time):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Create `.venv` and sync dependencies:

```bash
./setup.sh
```

3. Configure environment variables (example):

```bash
export PICO_VOICE_ACCESS_KEY="..."
export PORCUPINE_PPN_FILE="/absolute/path/to/hey-pomo.ppn"
export PORCUPINE_PV_FILE="/absolute/path/to/porcupine_params_de.pv"

# Optional STT config
export WHISPER_MODEL_SIZE="small"      # tiny|base|small|medium|large-v3
export WHISPER_DEVICE="cpu"            # cpu|cuda|auto
export WHISPER_COMPUTE_TYPE="int8"     # int8|float16|float32
export WHISPER_LANGUAGE="de"           # "auto"/"none" for auto-detect
export WHISPER_BEAM_SIZE="5"
export WHISPER_VAD_FILTER="true"

# Optional TTS config
export ENABLE_TTS="true"
export TTS_MODEL_PATH="thorsten_vits/model_file.pth"
export TTS_CONFIG_PATH="thorsten_vits/config.json"
# if files are missing, they are downloaded automatically:
# export TTS_HF_REPO_ID="Thorsten-Voice/VITS"
# export TTS_HF_LOCAL_DIR="thorsten_vits"
# export TTS_OUTPUT_DEVICE="0"         # optional sounddevice output index
# export TTS_GPU="false"
```

The wake-word env vars map to `WakeWordConfig` as:
- `PICO_VOICE_ACCESS_KEY` -> `pico_voice_access_key`
- `PORCUPINE_PPN_FILE` -> `porcupine_wake_word_file`
- `PORCUPINE_PV_FILE` -> `porcupine_model_params_file`

## Run

```bash
source .env
uv run python src/main.py
```

## Run diagnostics

Use this when tuning VAD sensitivity:

```bash
source .env
uv run python src/audio-diagnostic.py
```

## Notes

- This is currently a wake-word + transcription foundation. Pomodoro session logic is not implemented yet.
- The wake-word module is reusable and event-driven; see `src/wake_word/README.md`.

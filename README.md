# pomodoro-bot

Voice-driven pomodoro assistant prototype.

Current runtime pipeline:
- wake-word + utterance capture (`stt`)
- transcription (`faster-whisper`)
- optional local LLM response (`llm`)
- optional TTS playback (`tts`)
- built-in UI server (`server`) serving `web_ui/<ui>/index.html` + websocket updates

## Project layout

- `src/main.py`: app entrypoint and orchestration.
- `src/stt/`: wake-word capture + STT foundation. See `src/stt/README.md`.
- `src/llm/`: local LLM config/download/backend/parser/service. See `src/llm/README.md`.
- `src/tts/`: TTS model loading + playback service. See `src/tts/README.md`.
- `src/oracle/`: optional environment context providers (sensors + calendar).
- `src/pomodoro/`: pomodoro session runtime (`start/pause/continue/abort`) and countdown state.
- `src/server/`: static UI + websocket server runtime.
- `web_ui/`: browser UIs (`jarvis/`, `miro/`) served by `src/server`.
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

## Build Artifact Behavior

- The packaged binary bundles Porcupine default package assets from `pvporcupine` (keyword resources + native libraries) so startup can reach app config loading.
- `config.toml` is not embedded in the one-file executable. Provide it externally via `APP_CONFIG_FILE` or place it next to the binary.
- Custom wake-word assets configured in `config.toml` (`wake_word.ppn_file`, `wake_word.pv_file`) are not bundled and must be present on the target machine.
- App model directories under `models/` are not bundled.
- LLM/TTS model files are expected to be downloaded on demand from Hugging Face when configured.

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

Configure runtime settings in `config.toml` (non-secret values).

The repo now includes a default `config.toml` with sections for:
- `wake_word`
- `stt`
- `tts`
- `llm`
- `ui_server`
- `oracle`

UI selection settings:
- `ui_server.ui`: built-in UI variant (`jarvis` or `miro`)
- `ui_server.index_file`: optional explicit index file path override

Required first edit in `config.toml`:
- `wake_word.ppn_file`
- `wake_word.pv_file`

Set only secrets in `.env` (or your shell), for example:

```bash
export PICO_VOICE_ACCESS_KEY="..."
# optional
# export HF_TOKEN="..."
# required only when ORACLE_GOOGLE_CALENDAR_ENABLED=true:
# export ORACLE_GOOGLE_CALENDAR_ID="primary"
# export ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE="/absolute/path/to/service-account.json"
```

If you want to use a different config file path:

```bash
export APP_CONFIG_FILE="/absolute/path/to/config.toml"
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

# Deployment Guide — Pomodoro Bot

> **Generated:** 2026-02-28

## Overview

Pomodoro Bot is deployed as a single self-contained binary built with PyInstaller for arm64 (Raspberry Pi 5 / Debian Bookworm). The CI/CD pipeline runs on GitHub Actions using Docker QEMU emulation to produce a native arm64 binary without requiring access to a Pi.

## CI/CD Pipeline

**Trigger:** `git push --tags v*` (e.g. `git tag v1.2.3 && git push --tags`)

**Workflow:** `.github/workflows/release.yml`

```
tag push (v*)
    │
    ▼
┌─────────────────────────────────────────────────┐
│ Job: build (ubuntu-latest)                       │
│                                                  │
│  1. Checkout repository                          │
│  2. Set up QEMU (arm64 emulation)               │
│  3. Set up Docker Buildx                         │
│  4. Run build.sh inside:                         │
│     python:3.11-bookworm @ linux/arm64          │
│     (QEMU-emulated ARM64 container)             │
│     - apt install build-essential patchelf etc. │
│     - pip install uv                            │
│     - CMAKE_ARGS: disable native CPU features  │
│       for QEMU compatibility (-DGGML_NATIVE=OFF)│
│     - ./build.sh (PyInstaller --onefile)        │
│  5. Copy dist/archive.tar.gz → out/archive-arm64.tar.gz │
│  6. Upload artifact                              │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│ Job: release (ubuntu-latest, needs: build)       │
│                                                  │
│  1. Download all build artifacts                 │
│  2. Create GitHub Release (auto-generate notes)  │
│  3. Upload archive-arm64.tar.gz as release asset │
└─────────────────────────────────────────────────┘
```

### Important CI Notes

- `CMAKE_ARGS=-DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8-a` — prevents QEMU from detecting unsupported ARM dotprod instructions during emulated build
- The build image is `python:3.11-bookworm` for target ABI compatibility
- The workflow uses `softprops/action-gh-release@v2` with `generate_release_notes: true`

## Release Process

```bash
# 1. Ensure tests pass
uv run pytest tests/

# 2. Tag the release
git tag v1.2.3

# 3. Push tag to trigger CI build
git push --tags

# 4. Monitor CI at: https://github.com/dranoel2010/pomodoro-bot/actions
# 5. Release artifact appears at: https://github.com/dranoel2010/pomodoro-bot/releases
```

## Installing a Release on Raspberry Pi

### Fresh Install

```bash
# Prerequisites
sudo apt update
sudo apt install -y libasound2

# Create install directory
mkdir pomodoro-bot
cd pomodoro-bot

# Download latest release (replace URL with actual release asset URL)
curl -L -o pomodoro-bot-release.tar.gz \
  https://github.com/dranoel2010/pomodoro-bot/releases/latest/download/archive-arm64.tar.gz

# Extract
tar -xzf pomodoro-bot-release.tar.gz

# The extracted directory contains:
#   main          — executable
#   config.toml   — default runtime config
#   .env          — secrets template
```

### Post-Install Configuration

```bash
# 1. Place your Picovoice model files
mkdir -p models/sst
cp /path/to/hey-pomo.ppn models/sst/
cp /path/to/porcupine_params_de.pv models/sst/

# 2. Place your LLM model
mkdir -p models/llm/qwen3
cp /path/to/Qwen3-1.7B-Q4_K_M.gguf models/llm/qwen3/

# 3. Place your TTS model
mkdir -p models/tts
cp -r /path/to/thorsten-piper models/tts/

# 4. Edit config.toml:
#    [wake_word]
#    ppn_file = "models/sst/hey-pomo.ppn"
#    pv_file = "models/sst/porcupine_params_de.pv"

# 5. Set secrets in .env:
#    PICO_VOICE_ACCESS_KEY="your-key"

# 6. Run
source .env
./main
```

## Running as a Systemd Service (Raspberry Pi)

To run Pomodoro Bot automatically at boot:

```ini
# /etc/systemd/system/pomodoro-bot.service
[Unit]
Description=Pomodoro Bot Voice Assistant
After=sound.target network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/pomodoro-bot
EnvironmentFile=/home/pi/pomodoro-bot/.env
ExecStart=/home/pi/pomodoro-bot/main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable pomodoro-bot
sudo systemctl start pomodoro-bot
sudo systemctl status pomodoro-bot
```

## Performance Tuning (Raspberry Pi 5)

After deployment, apply Pi 5 performance optimisations:

```bash
# Apply performance CPU governor (persists until reboot unless made permanent)
sudo /home/pi/pomodoro-bot/scripts/pi5_cpu_tuning.sh apply

# Build native llama.cpp for better LLM throughput
# (run once after install, rebuilds .so used by the virtualenv)
./scripts/pi5_build_optimized_inference.sh
```

### Recommended `config.toml` for Pi 5

```toml
[stt]
model_size = "base"
compute_type = "int8"
cpu_threads = 2
beam_size = 1
vad_filter = true
cpu_cores = [0]

[llm]
n_threads = 3
n_threads_batch = 3
n_batch = 512
n_ctx = 2048
max_tokens = 128
cpu_affinity_mode = "pinned"
cpu_cores = [1, 2]
fast_path_enabled = true

[tts]
cpu_cores = [3]
```

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `PICO_VOICE_ACCESS_KEY` | **Yes** | Picovoice console access key |
| `HF_TOKEN` | No | Hugging Face token for private model downloads |
| `ORACLE_GOOGLE_CALENDAR_ID` | No | Calendar ID (e.g. `primary`) for Google Calendar |
| `ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE` | No | Absolute path to Google service account JSON |
| `APP_CONFIG_FILE` | No | Override default `config.toml` path |

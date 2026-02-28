# Project Overview — Pomodoro Bot

> **Generated:** 2026-02-28

## What is Pomodoro Bot?

Pomodoro Bot is a **local-first voice assistant** designed for focus work and time management. It runs entirely on a Raspberry Pi 5 (ARM64) — no cloud services required for the core voice pipeline.

Speak a wake-word ("Hey Pomo") and then issue hands-free commands to:
- Start / pause / stop Pomodoro sessions and countdown timers
- Query your Google Calendar for upcoming events
- Get spoken time and environmental context (air quality, ambient light)

All speech recognition, language understanding, and TTS synthesis run locally on-device using quantised open-source models optimised for the Pi 5's 4-core ARM Cortex-A76.

## Tech Stack Summary

| Area | Technology |
|------|-----------|
| Runtime | Python 3.13+, asyncio + multiprocessing (spawn) |
| Package manager | uv (locked with uv.lock) |
| Wake-word | Picovoice Porcupine (proprietary ARM64 binary) |
| Transcription (STT) | faster-whisper (int8, base/small/medium model) |
| Language model | llama-cpp-python + GGUF (Qwen3-1.7B-Q4_K_M) |
| TTS | piper-tts + sounddevice (Thorsten German voice) |
| Web UI | Vanilla HTML/JS/CSS, WebSocket push |
| Calendar | Google Calendar API (optional) |
| Sensors | ENS160, ADS1115/TEMT6000 via I²C (optional) |
| Build | PyInstaller one-file arm64 binary |
| CI/CD | GitHub Actions (Docker/QEMU arm64 + GitHub Releases) |

## Architecture Classification

| Property | Value |
|----------|-------|
| Repository structure | Monolith |
| Architecture pattern | Event-driven daemon with spawn-isolated ML workers |
| Process model | Main asyncio loop + 3 spawned ML worker processes |
| Language | Python 3.13+ |
| Primary target | Raspberry Pi 5 (ARM64 / Debian Bookworm) |
| Secondary target | macOS (development) |
| Deployment format | PyInstaller one-file binary + config archive |

## Module Summary

| Module | Path | Purpose |
|--------|------|---------|
| Entry point | `src/main.py` | App startup, composition root, worker factories |
| Runtime engine | `src/runtime/` | Event loop, utterance pipeline, worker lifecycle |
| LLM | `src/llm/` | Local LLM inference, parser, fast-path bypass |
| STT | `src/stt/` | Wake-word + transcription pipeline |
| TTS | `src/tts/` | Speech synthesis + audio playback |
| Oracle | `src/oracle/` | Calendar and sensor context injection |
| Pomodoro | `src/pomodoro/` | Timer and Pomodoro phase state machine |
| Server | `src/server/` | WebSocket UI broadcaster + HTTP static server |
| Contracts | `src/contracts/` | Canonical tool names + UI protocol constants |
| Shared | `src/shared/` | Cross-module defaults and env key constants |
| Web UI | `web_ui/` | Browser UIs (jarvis, miro variants) |
| Scripts | `scripts/` | Raspberry Pi 5 performance toolkit |

## Getting Started

See [Development Guide](./development-guide.md) for full setup instructions.

**Quick start (macOS):**

```bash
brew install uv python@3.11 portaudio git
git clone https://github.com/dranoel2010/pomodoro-bot.git
cd pomodoro-bot
./setup.sh
source .venv/bin/activate
cp .env.dist .env           # edit with your Picovoice access key
# edit config.toml: set wake_word.ppn_file and wake_word.pv_file
source .env
uv run python src/main.py
```

Then open `http://127.0.0.1:8765` in your browser.

## Documentation Index

- [Architecture](./architecture.md) — system design, component overview, critical constraints
- [Source Tree Analysis](./source-tree-analysis.md) — annotated directory tree
- [Development Guide](./development-guide.md) — setup, run, test, build
- [Deployment Guide](./deployment-guide.md) — CI/CD pipeline, Pi release process
- [Project Context](../_bmad-output/project-context.md) — AI agent rules and implementation conventions

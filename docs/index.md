# Project Documentation Index — Pomodoro Bot

> **Generated:** 2026-02-28 | Scan level: Quick | Mode: initial_scan

## Project Overview

- **Type:** Monolith — single Python daemon
- **Primary Language:** Python 3.13+
- **Architecture:** Event-driven service with spawn-isolated ML workers
- **Target:** Raspberry Pi 5 (ARM64 / Debian Bookworm)

## Quick Reference

- **Tech Stack:** Python + llama-cpp-python + faster-whisper + piper-tts + pvporcupine + websockets
- **Entry Point:** `src/main.py`
- **Architecture Pattern:** Asyncio event loop + 3 spawned ML worker processes
- **Package Manager:** uv (locked via `uv.lock`)
- **Run:** `source .env && uv run python src/main.py`
- **Test:** `uv run pytest tests/`
- **Build:** `./build.sh` → `dist/main` (arm64 binary)

## Generated Documentation

- [Project Overview](./project-overview.md) — executive summary, tech stack, module map
- [Architecture](./architecture.md) — system design, component diagrams, critical constraints
- [Source Tree Analysis](./source-tree-analysis.md) — annotated directory structure with purpose notes
- [Development Guide](./development-guide.md) — setup, run, test, build, CPU tuning
- [Deployment Guide](./deployment-guide.md) — CI/CD pipeline, Pi release, systemd service setup
- [Project Context](../_bmad-output/project-context.md) — AI agent implementation rules (47+ constraints)

## Existing Documentation (Source)

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Project overview, setup steps, run commands |
| [src/runtime/README.md](../src/runtime/README.md) | Runtime engine internals |
| [src/llm/README.md](../src/llm/README.md) | LLM module integration notes |
| [src/stt/README.md](../src/stt/README.md) | STT module integration notes |
| [src/tts/README.md](../src/tts/README.md) | TTS module integration notes |
| [src/oracle/README.md](../src/oracle/README.md) | Oracle context module notes |
| [src/pomodoro/README.md](../src/pomodoro/README.md) | Pomodoro timer state machine notes |
| [src/server/README.md](../src/server/README.md) | UI server notes |
| [src/contracts/README.md](../src/contracts/README.md) | Tool contract and tool naming conventions |
| [src/shared/README.md](../src/shared/README.md) | Shared constants notes |
| [src/debug/README.md](../src/debug/README.md) | Audio diagnostic tool notes |
| [tests/README.md](../tests/README.md) | Test suite overview |
| [web_ui/README.md](../web_ui/README.md) | Web UI variants documentation |

## Getting Started

**From source (macOS):**

```bash
brew install uv python@3.11 portaudio git
git clone https://github.com/dranoel2010/pomodoro-bot.git
cd pomodoro-bot
./setup.sh
cp .env.dist .env          # add your PICO_VOICE_ACCESS_KEY
# edit config.toml: set wake_word.ppn_file and wake_word.pv_file
source .env
uv run python src/main.py
# Open http://127.0.0.1:8765 in browser
```

**From release (Raspberry Pi):**

```bash
sudo apt install -y libasound2
mkdir pomodoro-bot && cd pomodoro-bot
# download latest archive-arm64.tar.gz from GitHub Releases
tar -xzf archive-arm64.tar.gz
# place models/, edit config.toml, edit .env
source .env && ./main
```

See [Development Guide](./development-guide.md) and [Deployment Guide](./deployment-guide.md) for complete instructions.

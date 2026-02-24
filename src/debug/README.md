# debug module

## Purpose
Manual diagnostics and tuning utilities for audio capture behavior.

## Key files
- `audio_diagnostic.py`: interactive VAD tuning tool that samples ambient noise and speech levels.

## Configuration
Uses the normal runtime config and secrets:
- `config.toml` (`wake_word` section)
- `PICO_VOICE_ACCESS_KEY`

## Integration notes
- Standalone utility; it does not run the main runtime loop.
- Run with `uv run python src/debug/audio_diagnostic.py`.

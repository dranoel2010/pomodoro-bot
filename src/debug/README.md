# debug module

## Purpose
Manual diagnostics and tuning utilities for local runtime behavior.

## Key files
- `audio_diagnostic.py`: interactive VAD tuning tool that samples ambient noise and speech levels.
- `prompt_benchmark.py`: real-model benchmark for comparing system prompt versions on speed and tool-call correctness.

## Configuration
Uses the normal runtime config and secrets:
- `config.toml` (`wake_word` and `llm` sections)
- `PICO_VOICE_ACCESS_KEY` (for `audio_diagnostic.py`)
- `HF_TOKEN` (optional if model download is needed)

## Prompt benchmark usage
Run against the system prompt in `config.toml`:

```bash
UV_CACHE_DIR=.uv-cache uv run python src/debug/prompt_benchmark.py
```

Compare multiple prompt files directly:

```bash
UV_CACHE_DIR=.uv-cache uv run python src/debug/prompt_benchmark.py \
  --system-prompts prompts/system_prompt_v1.md prompts/system_prompt_v2.md prompts/system_prompt_v3.md \
  --runs 2 \
  --warmup-runs 1 \
  --json-out build/prompt-benchmark.json
```

Quick smoke run:

```bash
UV_CACHE_DIR=.uv-cache uv run python src/debug/prompt_benchmark.py --suite smoke --runs 1
```

### What it checks
- Wide built-in prompt suite across timer, pomodoro, calendar, and non-tool prompts.
- Per-run assertions for expected tool call behavior:
  - expected `tool_call.name`
  - required argument keys
  - exact/regex argument constraints (for duration, `start_time`, `time_range`, etc.)
  - expected `tool_call = null` for non-action prompts
- Per-run speed metrics:
  - latency (ms)
  - completion tokens
  - completion tokens/sec
  - finish reason
- Ranked summary across prompt versions by accuracy first, then speed.

### Exit behavior
- By default, exits non-zero if any assertion fails.
- Use `--allow-failures` to always return `0` and only inspect report output.
- Use `--min-run-pass-rate` to enforce an explicit threshold (for CI gate checks).

## Integration notes
- Standalone utilities; they do not run the main runtime loop.
- `prompt_benchmark.py` executes real model calls only (no mocked completion path).

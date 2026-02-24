# tests module

## Purpose
Automated test suite for runtime behavior, parser rules, server routing, and configuration loading.

## Key files
- `config/`: app config parsing and validation tests.
- `llm/`: parser and LLM service characterization tests.
- `oracle/`: provider and oracle context tests.
- `pomodoro/`: timer state-machine characterization tests.
- `runtime/`: runtime dispatch, tool safety, and tick behavior tests.
- `server/`: static file, event, and server configuration tests.

## Configuration
Tests run with `uv run pytest`.
Some optional integrations are mocked or skipped when external dependencies are unavailable.

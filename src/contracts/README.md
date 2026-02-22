# contracts module

## Purpose
Shared constants that define stable contracts between parser, runtime, and UI layers.

## Key files
- `tool_contract.py`: canonical tool names, intent mappings, and grammar helpers.
- `ui_protocol.py`: websocket event names and runtime state constants.

## Configuration
No direct configuration.

## Integration notes
- Imported by `src/llm/` for tool-name parsing and grammar generation.
- Imported by `src/runtime/` and `src/server/` for consistent event payloads.

# runtime module

## Purpose
Application orchestration loop that connects wake-word events, STT/LLM/TTS processing, tool dispatch, and UI updates.

## Key files
- `loop.py`: `RuntimeEngine` lifecycle and event loop.
- `utterance.py`: STT -> LLM -> tool-call -> TTS utterance processing.
- `tool_dispatch.py`: timer/pomodoro/calendar tool call execution.
- `ticks.py`: completion/tick handling for timers.
- `ui.py`: UI publishing facade.
- `messages.py`: default German status and fallback messaging.
- `calendar_tools.py`: calendar argument parsing and runtime handlers.

## Configuration
Consumes the already-parsed `AppConfig` passed in by `src/main.py`.
No module-specific environment variables.

## Integration notes
- Uses one worker thread for utterance processing to avoid overlapping requests.
- Publishes startup sync state for both timer channels.
- Continues operating if optional services (oracle/ui/tts/llm) are not available.

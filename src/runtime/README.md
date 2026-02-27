# runtime module

## Purpose
Pipecat-only orchestration loop that connects wake-word events, STT/LLM/TTS stages, tool dispatch, and UI updates.

## Key files
- `pipecat_engine.py`: `PipecatRuntimeEngine` lifecycle, wake-word event loop, and Pipecat pipeline bridge.
- `tool_dispatch.py`: timer/pomodoro/calendar tool call execution.
- `ticks.py`: completion/tick handling for timers.
- `ui.py`: UI publishing facade.
- `messages.py`: default German status and fallback messaging.
- `calendar_tools.py`: calendar argument parsing and runtime handlers.

## Configuration
Consumes parsed `AppConfig` from `src/main.py`.
No module-specific environment variables.

## Integration notes
- Uses Pipecat `Pipeline`, `PipelineTask`, and `PipelineRunner` as runtime execution engine.
- CPU-intensive STT/LLM/TTS work remains in dedicated worker processes.
- Optional deterministic LLM fast-path can bypass llama.cpp for clear timer/pomodoro/calendar commands.
- Runtime logs utterance stage metrics (`stt_ms`, `llm_ms`, `tts_ms`, total duration).
- Publishes startup sync state for both timer channels.

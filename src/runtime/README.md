# runtime module

## Purpose
Application orchestration loop that connects wake-word events, STT/LLM/TTS processing, tool dispatch, and UI updates.

## Key files
- `engine.py`: `RuntimeEngine` lifecycle and event loop.
- Protocol interfaces (`STTClient`, `LLMClient`, `TTSClient`) live in `src/contracts/pipeline.py` — not in this package.
- `utterance.py`: STT -> LLM -> tool-call -> TTS utterance processing.
- `ticks.py`: completion/tick handling for timers.
- `ui.py`: UI publishing facade.
- `tools/dispatch.py`: timer/pomodoro/calendar tool call execution.
- `tools/messages.py`: default German status and fallback messaging.
- `tools/calendar.py`: calendar argument parsing and runtime handlers.
- `workers/stt.py`: STT process worker plus `create_stt_worker(...)` startup factory.
- `workers/llm.py`: LLM process worker, affinity shaping, and `create_llm_worker(...)` startup factory.
- `workers/tts.py`: TTS process worker plus `create_tts_worker(...)` startup factory.
- `workers/core.py`: shared process worker lifecycle/restart primitives.
- `engine.py` also exposes `RuntimeComponents` + composition helpers to keep dependency wiring separate from orchestration logic.

## Configuration
Consumes the already-parsed `AppConfig` passed in by `src/main.py`.
No module-specific environment variables.

## Integration notes
- Uses one orchestration thread for utterance sequencing to avoid overlapping requests.
- CPU-intensive STT/LLM/TTS work runs in dedicated worker processes.
- Worker startup concerns (enabled/disabled gating, `StartupError` wrapping, process wiring) are owned by `runtime.workers.*`.
- Worker process state is encapsulated inside process-local runtime objects managed by `workers/core.py`; worker modules do not use mutable module-level singleton instances.
- Worker core uses typed request/response envelopes plus explicit worker exceptions (`WorkerInitError`, `WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError`).
- Optional deterministic LLM fast-path can bypass llama.cpp for clear timer/pomodoro/calendar commands.
- Utterance pipeline logs stage metrics (`stt_ms`, `llm_ms`, `tts_ms`, total duration).
- Publishes startup sync state for both timer channels.
- Continues operating if optional services (oracle/ui/tts/llm) are not available.

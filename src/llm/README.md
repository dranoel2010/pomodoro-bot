# llm module

Local LLM module for generating structured assistant responses.

## Purpose

- Resolve model file location from typed application config.
- Download missing GGUF model files from Hugging Face when configured.
- Run llama.cpp chat completion with grammar-constrained JSON output.
- Parse and normalize responses into a stable shape.

## Main components

- `config.py`: `LLMConfig` and typed model resolution helpers.
- `model_store.py`: Hugging Face model download/validation helpers.
- `llama_backend.py`: llama.cpp backend and grammar.
- `parser.py`: schema validation and response normalization.
- `service.py`: `PomodoroAssistantLLM` high-level API.
- `types.py`: structured response and environment context types.

## Configuration inputs

Configured via `config.toml` (`[llm]` section):
- `enabled`
- `model_path`
- `hf_filename`
- `hf_repo_id`
- `hf_revision`
- `system_prompt`
- `n_threads`
- `n_ctx`
- `n_batch`
- `temperature`
- `top_p`
- `repeat_penalty`
- `verbose`

Secret via environment:
- `HF_TOKEN` (optional Hugging Face token)

## Integration

`src/main.py` sends transcribed utterance text to `PomodoroAssistantLLM` and optionally speaks `assistant_text` via `tts`.
When oracle integrations are enabled, `main.py` passes `EnvironmentContext` (air quality, light level, upcoming events) and the LLM service renders configured ENVIRONMENT placeholders in the system prompt template before inference.
Tool calls are executed by the pomodoro runtime (`timer_start`, `timer_pause`, `timer_continue`, `timer_abort`) with legacy aliases (`timer_stop`, `timer_reset`) still accepted.

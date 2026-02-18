# llm module

Local LLM module for generating structured assistant responses.

## Purpose

- Resolve model file location from environment.
- Download missing GGUF model files from Hugging Face when configured.
- Run llama.cpp chat completion with grammar-constrained JSON output.
- Parse and normalize responses into a stable shape.

## Main components

- `config.py`: `LLMConfig` and env-driven model resolution.
- `model_store.py`: Hugging Face model download/validation helpers.
- `llama_backend.py`: llama.cpp backend and grammar.
- `parser.py`: schema validation and response normalization.
- `service.py`: `PomodoroAssistantLLM` high-level API.
- `types.py`: structured response and environment context types.

## Environment variables

Core:
- `LLM_MODEL_PATH`: directory where model file is expected.
- `LLM_HF_FILENAME`: GGUF filename expected inside `LLM_MODEL_PATH`.

Download (used when the target file is missing):
- `LLM_HF_REPO_ID`: Hugging Face repo to download from.
- `LLM_HF_REVISION`: optional branch/tag/commit.
- `HF_TOKEN`: optional auth token.

Runtime tuning:
- `LLM_N_THREADS` (default `4`)
- `LLM_N_CTX` (default `2048`)
- `LLM_N_BATCH` (default `256`)
- `LLM_TEMPERATURE` (default `0.2`)
- `LLM_TOP_P` (default `0.9`)
- `LLM_REPEAT_PENALTY` (default `1.1`)
- `LLM_VERBOSE` (`true`/`false`)
- `ENABLE_LLM` optional explicit enable switch.

## Integration

`src/main.py` sends transcribed utterance text to `PomodoroAssistantLLM` and optionally speaks `assistant_text` via `tts`.
Tool call execution is intentionally skipped for now.

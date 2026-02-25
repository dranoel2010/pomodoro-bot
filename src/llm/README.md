# llm module

## Purpose
Local LLM integration that generates structured assistant replies and normalized tool calls.

## Key files
- `config.py`: validates model/runtime settings and resolves local model paths.
- `model_store.py`: downloads and validates GGUF files from Hugging Face.
- `llama_backend.py`: llama.cpp wrapper with grammar-constrained JSON output.
- `fast_path.py`: deterministic command routing that can bypass llama.cpp entirely.
- `parser.py`: JSON normalization with intent fallback behavior.
- `service.py`: `PomodoroAssistantLLM` orchestration entrypoint.
- `types.py`: typed response and environment context payloads.

## Configuration
From `config.toml` (`[llm]`):
- `enabled`
- `model_path`
- `hf_filename`
- `hf_repo_id`
- `hf_revision`
- `system_prompt`
- `n_threads`
- `n_threads_batch`
- `n_ctx`
- `n_batch`
- `n_ubatch`
- `temperature`
- `top_p`
- `top_k`
- `min_p`
- `repeat_penalty`
- `use_mmap`
- `use_mlock`
- `verbose`
- `fast_path_enabled`
- `cpu_affinity_mode`
- `shared_cpu_reserve_cores`
- `cpu_cores`

Secrets from environment:
- `HF_TOKEN` (optional for private model access)
- `LLM_SYSTEM_PROMPT` (optional fallback prompt path)

## Integration notes
- `src/main.py` initializes the module only when `llm.enabled = true`.
- Runtime tool execution uses canonical tool names from `src/contracts/tool_contract.py`.
- Parser fallback inference is intentionally enabled when model output is invalid or incomplete.
- Completion logs include token accounting plus throughput metrics (duration and completion tokens/sec).

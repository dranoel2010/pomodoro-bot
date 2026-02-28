from __future__ import annotations

import logging

from .config import LLMConfig


def create_llm_config(*, llm, hf_token: str | None, logger: logging.Logger) -> LLMConfig:
    return LLMConfig.from_sources(
        model_dir=llm.model_path,
        hf_filename=llm.hf_filename,
        hf_repo_id=llm.hf_repo_id or None,
        hf_revision=llm.hf_revision or None,
        hf_token=hf_token,
        system_prompt_path=llm.system_prompt or None,
        max_tokens=llm.max_tokens,
        n_threads=llm.n_threads,
        n_threads_batch=llm.n_threads_batch,
        n_ctx=llm.n_ctx,
        n_batch=llm.n_batch,
        n_ubatch=llm.n_ubatch,
        temperature=llm.temperature,
        top_p=llm.top_p,
        top_k=llm.top_k,
        min_p=llm.min_p,
        repeat_penalty=llm.repeat_penalty,
        use_mmap=llm.use_mmap,
        use_mlock=llm.use_mlock,
        verbose=llm.verbose,
        logger=logger,
    )

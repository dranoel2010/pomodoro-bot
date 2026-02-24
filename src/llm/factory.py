"""Startup factory for process-backed LLM client construction."""

from __future__ import annotations

import logging
from multiprocessing.queues import Queue as MPQueue
from typing import TYPE_CHECKING

from contracts.errors import StartupError

from .config import ConfigurationError, LLMConfig

if TYPE_CHECKING:
    from app_config import LLMSettings
    from runtime.process_workers import ProcessLLMClient


def create_llm_client(
    *,
    llm: "LLMSettings",
    hf_token: str | None,
    log_queue: MPQueue,
    log_level: int,
    logger: logging.Logger,
) -> "ProcessLLMClient" | None:
    """Build process-backed LLM client when the feature is enabled."""

    if not llm.enabled:
        return None

    try:
        from runtime.process_workers import ProcessLLMClient
    except ImportError as error:
        raise StartupError(f"LLM module import error: {error}")

    try:
        llm_config = LLMConfig.from_sources(
            model_dir=llm.model_path,
            hf_filename=llm.hf_filename,
            hf_repo_id=llm.hf_repo_id or None,
            hf_revision=llm.hf_revision or None,
            hf_token=hf_token,
            system_prompt_path=llm.system_prompt or None,
            max_tokens=llm.max_tokens,
            n_threads=llm.n_threads,
            n_ctx=llm.n_ctx,
            n_batch=llm.n_batch,
            temperature=llm.temperature,
            top_p=llm.top_p,
            repeat_penalty=llm.repeat_penalty,
            verbose=llm.verbose,
            logger=logging.getLogger("llm.config"),
        )
    except ConfigurationError as error:
        raise StartupError(f"LLM configuration error: {error}")
    except Exception as error:
        raise StartupError(
            f"LLM configuration failed: {type(error).__name__}: {error}"
        )

    try:
        llm_client = ProcessLLMClient(
            config=llm_config,
            cpu_cores=llm.cpu_cores,
            logger=logging.getLogger("llm.process"),
            log_queue=log_queue,
            log_level=log_level,
        )
        logger.info("LLM enabled (model: %s)", llm_config.model_path)
        return llm_client
    except Exception as error:
        raise StartupError(
            f"LLM initialization failed: {type(error).__name__}: {error}"
        )

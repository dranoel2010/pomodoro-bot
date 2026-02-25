from __future__ import annotations

import logging
from multiprocessing.queues import Queue as MPQueue

from contracts import StartupError

from .config import ConfigurationError, LLMConfig


def create_llm_client(
    *,
    llm,
    hf_token: str | None,
    log_queue: MPQueue,
    log_level: int,
    logger: logging.Logger,
):
    if not llm.enabled:
        return None

    try:
        from runtime.process_workers import ProcessLLMClient

        llm_config = LLMConfig.from_sources(
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
            logger=logging.getLogger("llm.config"),
        )
        llm_client = ProcessLLMClient(
            config=llm_config,
            cpu_cores=llm.cpu_cores,
            cpu_affinity_mode=llm.cpu_affinity_mode,
            shared_cpu_reserve_cores=llm.shared_cpu_reserve_cores,
            logger=logging.getLogger("llm.process"),
            log_queue=log_queue,
            log_level=log_level,
        )
        logger.info("LLM enabled (model: %s)", llm_config.model_path)
        return llm_client
    except ConfigurationError as error:
        raise StartupError(f"LLM configuration error: {error}")
    except ImportError as error:
        raise StartupError(f"LLM module import error: {error}")
    except Exception as error:
        raise StartupError(
            f"LLM initialization failed: {type(error).__name__}: {error}"
        )

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from multiprocessing.queues import Queue as MPQueue
from typing import TYPE_CHECKING, Final, cast

from contracts import StartupError
from llm.config import ConfigurationError
from llm.factory import create_llm_config
from llm.types import LLMResult

from .core import _ProcessWorker

if TYPE_CHECKING:
    from llm.config import LLMConfig
    from llm.types import EnvironmentContext, StructuredResponse


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_AFFINITY_MODES: Final = frozenset({"pinned", "shared"})


# ---------------------------------------------------------------------------
# Worker-process state
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _WorkerConfig:
    """Validated, adjusted configuration passed into the worker process."""

    llm_config: LLMConfig
    cpu_cores: tuple[int, ...]


class _LLMProcess:
    """Encapsulates the LLM instance that lives inside the worker process."""

    def __init__(self, config: LLMConfig) -> None:
        from llm.service import PomodoroAssistantLLM

        self._llm = PomodoroAssistantLLM(config)

    def handle(self, payload: object) -> object:
        if not isinstance(payload, LLMPayload):
            raise ValueError(f"Expected LLMPayload, got {type(payload).__name__}")
        response = self._llm.run(
            payload.user_prompt,
            env=payload.env,
            extra_context=payload.extra_context,
            max_tokens=payload.max_tokens,
        )
        return LLMResult(response=response, tokens=self._llm.last_tokens)


def _create_llm_process(worker_config: _WorkerConfig) -> _LLMProcess:
    return _LLMProcess(worker_config.llm_config)


@dataclass(frozen=True, slots=True)
class LLMPayload:
    user_prompt: str
    env: EnvironmentContext | None = None
    extra_context: str | None = None
    max_tokens: int | None = None


# ---------------------------------------------------------------------------
# CPU affinity helpers
# ---------------------------------------------------------------------------


class AffinityConfigError(ValueError):
    """Raised when an invalid CPU affinity mode is supplied."""


def _resolve_worker_config(
    config: LLMConfig,
    *,
    cpu_cores: tuple[int, ...],
    cpu_affinity_mode: str,
    shared_cpu_reserve_cores: int,
    logger: logging.Logger,
) -> _WorkerConfig:
    mode = cpu_affinity_mode.strip().lower()
    if mode not in _VALID_AFFINITY_MODES:
        raise AffinityConfigError(
            f"Unsupported llm.cpu_affinity_mode={cpu_affinity_mode!r}; "
            f"expected one of {sorted(_VALID_AFFINITY_MODES)}."
        )

    if mode == "shared":
        return _resolve_shared_config(config, shared_cpu_reserve_cores, logger)

    return _resolve_pinned_config(config, cpu_cores, logger)


def _resolve_shared_config(
    config: LLMConfig,
    reserve_cores: int,
    logger: logging.Logger,
) -> _WorkerConfig:
    cpu_count = max(1, os.cpu_count() or config.n_threads)
    usable = max(1, cpu_count - max(0, reserve_cores))
    adjusted = _cap_threads(config, usable, logger, mode="shared")
    logger.info(
        "LLM worker: shared affinity mode — unpinned, may borrow idle cores "
        "(cpu_count=%d, reserve=%d, usable=%d)",
        cpu_count,
        reserve_cores,
        usable,
    )
    return _WorkerConfig(llm_config=adjusted, cpu_cores=())


def _resolve_pinned_config(
    config: LLMConfig,
    cpu_cores: tuple[int, ...],
    logger: logging.Logger,
) -> _WorkerConfig:
    if not cpu_cores:
        return _WorkerConfig(llm_config=config, cpu_cores=())
    adjusted = _cap_threads(config, len(cpu_cores), logger, mode="pinned")
    return _WorkerConfig(llm_config=adjusted, cpu_cores=cpu_cores)


def _cap_threads(
    config: LLMConfig,
    limit: int,
    logger: logging.Logger,
    *,
    mode: str,
) -> LLMConfig:
    adjusted = config
    if adjusted.n_threads > limit:
        adjusted = replace(adjusted, n_threads=limit)
        logger.info(
            "Adjusted llm.n_threads → %d (mode=%s, limit=%d)", limit, mode, limit
        )
    if adjusted.n_threads_batch is not None and adjusted.n_threads_batch > limit:
        adjusted = replace(adjusted, n_threads_batch=limit)
        logger.info(
            "Adjusted llm.n_threads_batch → %d (mode=%s, limit=%d)", limit, mode, limit
        )
    return adjusted


# ---------------------------------------------------------------------------
# Public worker interface
# ---------------------------------------------------------------------------


class LLMWorker:
    """Manages an out-of-process LLM instance."""

    _DEFAULT_CLOSE_TIMEOUT: Final[float] = 5.0

    def __init__(
        self,
        *,
        config: LLMConfig,
        cpu_cores: tuple[int, ...] = (),
        cpu_affinity_mode: str = "pinned",
        shared_cpu_reserve_cores: int = 1,
        logger: logging.Logger | None = None,
        log_queue: MPQueue | None = None,
        log_level: int = logging.INFO,
    ) -> None:
        worker_logger = logger or logging.getLogger("llm.process")
        worker_config = _resolve_worker_config(
            config,
            cpu_cores=cpu_cores,
            cpu_affinity_mode=cpu_affinity_mode,
            shared_cpu_reserve_cores=shared_cpu_reserve_cores,
            logger=worker_logger,
        )
        self._worker = _ProcessWorker(
            name="llm-worker",
            runtime_factory=_create_llm_process,
            runtime_args=(worker_config,),
            cpu_cores=worker_config.cpu_cores,
            log_queue=log_queue,
            log_level=log_level,
            logger=worker_logger,
        )
        self._last_tokens: int = 0

    def run(
        self,
        user_prompt: str,
        *,
        env: EnvironmentContext | None = None,
        extra_context: str | None = None,
        max_tokens: int | None = None,
    ) -> StructuredResponse:
        payload = LLMPayload(
            user_prompt=user_prompt,
            env=env,
            extra_context=extra_context,
            max_tokens=max_tokens,
        )
        result = cast("LLMResult", self._worker.call(payload))
        self._last_tokens = result.tokens
        return result.response

    @property
    def last_tokens(self) -> int:
        return self._last_tokens

    def close(self, timeout_seconds: float = _DEFAULT_CLOSE_TIMEOUT) -> None:
        self._worker.close(timeout_seconds=timeout_seconds)

    # Context-manager support so callers don't have to remember close().
    def __enter__(self) -> LLMWorker:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_llm_worker(
    *,
    llm,  # typed by caller via config schema — keep untyped here to avoid circular import
    hf_token: str | None,
    log_queue: MPQueue,
    log_level: int,
    logger: logging.Logger,
) -> LLMWorker | None:
    if not llm.enabled:
        return None

    try:
        llm_config = create_llm_config(
            llm=llm,
            hf_token=hf_token,
            logger=logging.getLogger("llm.config"),
        )
        worker = LLMWorker(
            config=llm_config,
            cpu_cores=tuple(llm.cpu_cores),
            cpu_affinity_mode=llm.cpu_affinity_mode,
            shared_cpu_reserve_cores=llm.shared_cpu_reserve_cores,
            logger=logging.getLogger("llm.process"),
            log_queue=log_queue,
            log_level=log_level,
        )
        logger.info("LLM enabled (model: %s)", llm_config.model_path)
        return worker

    except (ConfigurationError, AffinityConfigError) as exc:
        raise StartupError(f"LLM configuration error: {exc}") from exc
    except ImportError as exc:
        raise StartupError(f"LLM module import error: {exc}") from exc
    except Exception as exc:
        raise StartupError(
            f"LLM initialization failed: {type(exc).__name__}: {exc}"
        ) from exc

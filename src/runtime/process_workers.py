from __future__ import annotations

import concurrent.futures
import logging
import multiprocessing
import os
from dataclasses import replace
from logging.handlers import QueueHandler
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from llm.config import LLMConfig
    from llm.types import EnvironmentContext, StructuredResponse
    from stt.config import STTConfig
    from stt.events import Utterance
    from stt.stt import TranscriptionResult
    from tts.config import TTSConfig


def _configure_worker_logging(
    *,
    log_queue: multiprocessing.Queue[object] | None,
    log_level: int,
) -> None:
    if log_queue is None:
        return

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    root_logger.setLevel(log_level)
    root_logger.addHandler(QueueHandler(log_queue))


def _set_process_cpu_affinity(
    cpu_cores: tuple[int, ...],
    *,
    logger: logging.Logger,
) -> None:
    if not cpu_cores:
        return

    cores = sorted(set(cpu_cores))
    core_set = set(cores)

    if hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, core_set)
            logger.info("Pinned process to CPU cores: %s", cores)
            return
        except Exception as error:
            logger.warning("sched_setaffinity failed: %s", error)

    try:
        import psutil  # type: ignore[import-not-found]

        process = psutil.Process()
    except Exception as error:
        logger.warning(
            "CPU affinity requested (%s) but psutil is unavailable: %s",
            cores,
            error,
        )
        return

    cpu_affinity = getattr(process, "cpu_affinity", None)
    if not callable(cpu_affinity):
        logger.warning(
            "CPU affinity requested (%s) but unsupported on this platform.",
            cores,
        )
        return

    try:
        cpu_affinity(cores)
    except Exception as error:
        raise RuntimeError(
            f"Failed to pin worker to CPU cores {cores}: {error}"
        ) from error

    logger.info("Pinned process to CPU cores: %s", cores)


def _worker_ping() -> None:
    return None


_STT_INSTANCE: Any = None
_LLM_INSTANCE: Any = None
_TTS_INSTANCE: Any = None


def _init_stt_worker(
    config: "STTConfig",
    cpu_cores: tuple[int, ...],
    log_queue: multiprocessing.Queue[object] | None,
    log_level: int,
) -> None:
    global _STT_INSTANCE

    _configure_worker_logging(log_queue=log_queue, log_level=log_level)
    logger = logging.getLogger("stt.worker")
    _set_process_cpu_affinity(cpu_cores, logger=logger)

    from stt.stt import FasterWhisperSTT

    _STT_INSTANCE = FasterWhisperSTT(
        model_size=config.model_size,
        device=config.device,
        compute_type=config.compute_type,
        language=config.language,
        beam_size=config.beam_size,
        vad_filter=config.vad_filter,
        cpu_threads=config.cpu_threads,
        logger=logger,
    )


def _stt_task(utterance: object) -> object:
    if _STT_INSTANCE is None:
        raise RuntimeError("STT worker was not initialized.")
    return _STT_INSTANCE.transcribe(utterance)


def _init_llm_worker(
    config: "LLMConfig",
    cpu_cores: tuple[int, ...],
    log_queue: multiprocessing.Queue[object] | None,
    log_level: int,
) -> None:
    global _LLM_INSTANCE

    _configure_worker_logging(log_queue=log_queue, log_level=log_level)
    logger = logging.getLogger("llm.worker")
    _set_process_cpu_affinity(cpu_cores, logger=logger)

    from llm.service import PomodoroAssistantLLM

    _LLM_INSTANCE = PomodoroAssistantLLM(config)


def _llm_task(payload: dict[str, object]) -> object:
    if _LLM_INSTANCE is None:
        raise RuntimeError("LLM worker was not initialized.")

    user_prompt = payload.get("user_prompt")
    if not isinstance(user_prompt, str):
        raise RuntimeError("LLM payload is missing 'user_prompt'.")

    extra_context = payload.get("extra_context")
    if extra_context is not None and not isinstance(extra_context, str):
        extra_context = str(extra_context)

    max_tokens_raw = payload.get("max_tokens")
    if max_tokens_raw is not None and not isinstance(max_tokens_raw, int):
        raise RuntimeError("LLM payload has invalid 'max_tokens'.")

    return _LLM_INSTANCE.run(
        user_prompt,
        env=payload.get("env"),
        extra_context=extra_context,
        max_tokens=max_tokens_raw,
    )


def _init_tts_worker(
    config: "TTSConfig",
    cpu_cores: tuple[int, ...],
    log_queue: multiprocessing.Queue[object] | None,
    log_level: int,
) -> None:
    global _TTS_INSTANCE

    _configure_worker_logging(log_queue=log_queue, log_level=log_level)
    logger = logging.getLogger("tts.worker")
    _set_process_cpu_affinity(cpu_cores, logger=logger)

    from tts.engine import PiperTTSEngine
    from tts.output import SoundDeviceAudioOutput
    from tts.service import SpeechService

    _TTS_INSTANCE = SpeechService(
        engine=PiperTTSEngine(config=config, logger=logger.getChild("engine")),
        output=SoundDeviceAudioOutput(
            output_device_index=config.output_device_index,
            logger=logger.getChild("output"),
        ),
        logger=logger,
    )


def _tts_task(text: str) -> None:
    if _TTS_INSTANCE is None:
        raise RuntimeError("TTS worker was not initialized.")
    _TTS_INSTANCE.speak(text)


class _ProcessWorker:
    def __init__(
        self,
        *,
        name: str,
        task: Callable[[object], object],
        initializer: Callable[..., None],
        init_args: tuple[object, ...],
        logger: logging.Logger,
        startup_timeout_seconds: float = 30.0,
    ):
        self._name = name
        self._task = task
        self._logger = logger
        self._closed = False
        self._executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=1,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=initializer,
            initargs=init_args,
        )
        self._await_ready(timeout_seconds=startup_timeout_seconds)

    def _await_ready(self, *, timeout_seconds: float) -> None:
        future = self._executor.submit(_worker_ping)
        try:
            future.result(timeout=timeout_seconds)
            self._logger.info("%s worker ready", self._name)
        except concurrent.futures.TimeoutError as error:
            future.cancel()
            self.close()
            raise RuntimeError(f"{self._name} startup timed out.") from error
        except Exception as error:
            self.close()
            raise RuntimeError(
                f"{self._name} initialization failed: {error}"
            ) from error

    def call(self, payload: object, *, timeout_seconds: float = 120.0) -> object:
        if self._closed:
            raise RuntimeError(f"{self._name} worker is closed.")

        future = self._executor.submit(self._task, payload)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as error:
            future.cancel()
            raise RuntimeError(f"{self._name} worker timed out.") from error

    def close(self, timeout_seconds: float = 5.0) -> None:
        del timeout_seconds
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)


def _llm_config_for_worker(
    config: "LLMConfig",
    *,
    cpu_cores: tuple[int, ...],
    cpu_affinity_mode: str,
    shared_cpu_reserve_cores: int,
    logger: logging.Logger,
) -> tuple["LLMConfig", tuple[int, ...]]:
    mode = (cpu_affinity_mode or "pinned").strip().lower()
    if mode not in {"pinned", "shared"}:
        raise RuntimeError(
            f"Unsupported llm.cpu_affinity_mode={cpu_affinity_mode!r}; expected 'pinned' or 'shared'."
        )

    if mode == "shared":
        reserve = max(0, shared_cpu_reserve_cores)
        cpu_count = max(1, os.cpu_count() or config.n_threads)
        usable_cores = max(1, cpu_count - reserve)
        adjusted = config
        if adjusted.n_threads > usable_cores:
            adjusted = replace(adjusted, n_threads=usable_cores)
            logger.info(
                "Adjusted llm.n_threads to %d for shared affinity mode (cpu_count=%d reserve=%d)",
                usable_cores,
                cpu_count,
                reserve,
            )
        if (
            adjusted.n_threads_batch is not None
            and adjusted.n_threads_batch > usable_cores
        ):
            adjusted = replace(adjusted, n_threads_batch=usable_cores)
            logger.info(
                "Adjusted llm.n_threads_batch to %d for shared affinity mode",
                usable_cores,
            )
        logger.info(
            "LLM worker running in shared affinity mode: process is unpinned and may borrow idle CPU cores."
        )
        return adjusted, ()

    if not cpu_cores:
        return config, ()

    adjusted = config
    if adjusted.n_threads > len(cpu_cores):
        adjusted = replace(adjusted, n_threads=len(cpu_cores))
        logger.info(
            "Adjusted llm.n_threads to %d to match assigned CPU cores",
            len(cpu_cores),
        )
    if (
        adjusted.n_threads_batch is not None
        and adjusted.n_threads_batch > len(cpu_cores)
    ):
        adjusted = replace(adjusted, n_threads_batch=len(cpu_cores))
        logger.info(
            "Adjusted llm.n_threads_batch to %d to match assigned CPU cores",
            len(cpu_cores),
        )
    return adjusted, cpu_cores


class ProcessSTTClient:
    def __init__(
        self,
        *,
        config: "STTConfig",
        cpu_cores: tuple[int, ...] = (),
        logger: logging.Logger | None = None,
        log_queue: multiprocessing.Queue[object] | None = None,
        log_level: int = logging.INFO,
    ):
        worker_logger = logger or logging.getLogger("stt.process")
        self._worker = _ProcessWorker(
            name="stt-worker",
            task=_stt_task,
            initializer=_init_stt_worker,
            init_args=(config, cpu_cores, log_queue, log_level),
            logger=worker_logger,
        )

    def transcribe(self, utterance: "Utterance") -> "TranscriptionResult":
        from stt.stt import STTError

        try:
            return self._worker.call(utterance)
        except Exception as error:
            raise STTError(f"Process STT failed: {error}") from error

    def close(self, timeout_seconds: float = 5.0) -> None:
        self._worker.close(timeout_seconds=timeout_seconds)


class ProcessLLMClient:
    def __init__(
        self,
        *,
        config: "LLMConfig",
        cpu_cores: tuple[int, ...] = (),
        cpu_affinity_mode: str = "pinned",
        shared_cpu_reserve_cores: int = 1,
        logger: logging.Logger | None = None,
        log_queue: multiprocessing.Queue[object] | None = None,
        log_level: int = logging.INFO,
    ):
        worker_logger = logger or logging.getLogger("llm.process")
        llm_config, worker_cpu_cores = _llm_config_for_worker(
            config,
            cpu_cores=cpu_cores,
            cpu_affinity_mode=cpu_affinity_mode,
            shared_cpu_reserve_cores=shared_cpu_reserve_cores,
            logger=worker_logger,
        )
        self._worker = _ProcessWorker(
            name="llm-worker",
            task=_llm_task,
            initializer=_init_llm_worker,
            init_args=(llm_config, worker_cpu_cores, log_queue, log_level),
            logger=worker_logger,
        )

    def run(
        self,
        user_prompt: str,
        *,
        env: "EnvironmentContext" | None = None,
        extra_context: str | None = None,
        max_tokens: int | None = None,
    ) -> "StructuredResponse":
        payload: dict[str, object] = {
            "user_prompt": user_prompt,
            "env": env,
            "extra_context": extra_context,
            "max_tokens": max_tokens,
        }
        return self._worker.call(payload)

    def close(self, timeout_seconds: float = 5.0) -> None:
        self._worker.close(timeout_seconds=timeout_seconds)


class ProcessTTSClient:
    def __init__(
        self,
        *,
        config: "TTSConfig",
        cpu_cores: tuple[int, ...] = (),
        logger: logging.Logger | None = None,
        log_queue: multiprocessing.Queue[object] | None = None,
        log_level: int = logging.INFO,
    ):
        worker_logger = logger or logging.getLogger("tts.process")
        self._worker = _ProcessWorker(
            name="tts-worker",
            task=_tts_task,
            initializer=_init_tts_worker,
            init_args=(config, cpu_cores, log_queue, log_level),
            logger=worker_logger,
        )

    def speak(self, text: str) -> None:
        from tts.engine import TTSError

        try:
            self._worker.call(text)
        except Exception as error:
            raise TTSError(f"Process TTS failed: {error}") from error

    def close(self, timeout_seconds: float = 5.0) -> None:
        self._worker.close(timeout_seconds=timeout_seconds)

"""Dedicated process workers for STT, LLM, and TTS runtime workloads."""

from __future__ import annotations

import logging
import multiprocessing
import os
import queue
import threading
from logging.handlers import QueueHandler
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from llm import EnvironmentContext, LLMConfig, StructuredResponse
    from stt import STTConfig, TranscriptionResult, Utterance
    from tts import TTSConfig


_READY = "ready"
_INIT_ERROR = "init_error"
_OK = "ok"
_ERROR = "error"
_SHUTDOWN = "__shutdown__"


def _configure_worker_logging(
    *,
    log_queue: Optional[multiprocessing.Queue[Any]],
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

    core_set = set(cpu_cores)
    if hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, core_set)
            logger.info("Pinned process to CPU cores: %s", sorted(core_set))
            return
        except Exception as error:
            logger.warning("Failed to set CPU affinity with sched_setaffinity: %s", error)

    try:
        import psutil  # type: ignore[import-not-found]

        process = psutil.Process()
        process.cpu_affinity(list(core_set))
        logger.info("Pinned process to CPU cores: %s", sorted(core_set))
        return
    except Exception:
        logger.warning(
            "CPU affinity requested (%s) but unsupported on this platform.",
            sorted(core_set),
        )


class _DedicatedProcessWorker:
    def __init__(
        self,
        *,
        name: str,
        target: Callable[..., None],
        target_args: tuple[Any, ...],
        logger: logging.Logger,
        startup_timeout_seconds: float = 30.0,
        log_queue: Optional[multiprocessing.Queue[Any]] = None,
        log_level: int = logging.INFO,
    ):
        self._name = name
        self._logger = logger
        self._rpc_lock = threading.Lock()
        self._closed = False

        ctx = multiprocessing.get_context("spawn")
        self._request_queue: multiprocessing.Queue[Any] = ctx.Queue()
        self._response_queue: multiprocessing.Queue[Any] = ctx.Queue()
        self._process = ctx.Process(
            name=name,
            target=target,
            args=(
                self._request_queue,
                self._response_queue,
                log_queue,
                log_level,
                *target_args,
            ),
            daemon=True,
        )
        self._process.start()
        self._await_ready(timeout_seconds=startup_timeout_seconds)

    def _await_ready(self, *, timeout_seconds: float) -> None:
        try:
            status, payload = self._response_queue.get(timeout=timeout_seconds)
        except queue.Empty as error:
            if not self._process.is_alive():
                raise RuntimeError(f"{self._name} failed to start (process exited).") from error
            raise RuntimeError(f"{self._name} startup timed out.") from error

        if status == _READY:
            self._logger.info("%s worker ready", self._name)
            return
        if status == _INIT_ERROR:
            raise RuntimeError(f"{self._name} initialization failed: {payload}")
        raise RuntimeError(f"{self._name} returned unexpected startup status: {status!r}")

    def call(self, payload: Any, *, timeout_seconds: float = 120.0) -> Any:
        with self._rpc_lock:
            self._ensure_alive()
            self._request_queue.put(payload)
            return self._await_result(timeout_seconds=timeout_seconds)

    def _await_result(self, *, timeout_seconds: float) -> Any:
        try:
            status, payload = self._response_queue.get(timeout=timeout_seconds)
        except queue.Empty as error:
            if not self._process.is_alive():
                raise RuntimeError(f"{self._name} worker exited unexpectedly.") from error
            raise RuntimeError(f"{self._name} worker timed out.") from error

        if status == _OK:
            return payload
        if status == _ERROR:
            raise RuntimeError(str(payload))
        raise RuntimeError(f"{self._name} worker returned invalid status: {status!r}")

    def _ensure_alive(self) -> None:
        if self._closed:
            raise RuntimeError(f"{self._name} worker is closed.")
        if not self._process.is_alive():
            raise RuntimeError(f"{self._name} worker is not running.")

    def close(self, timeout_seconds: float = 5.0) -> None:
        with self._rpc_lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._request_queue.put(_SHUTDOWN)
            except Exception:
                pass

            self._process.join(timeout=timeout_seconds)
            if self._process.is_alive():
                self._logger.warning(
                    "%s worker did not exit in %.1fs; terminating.",
                    self._name,
                    timeout_seconds,
                )
                self._process.terminate()
                self._process.join(timeout=1.0)


class ProcessSTTClient:
    """Process-backed STT client compatible with `FasterWhisperSTT.transcribe`."""

    def __init__(
        self,
        *,
        config: "STTConfig",
        cpu_cores: tuple[int, ...] = (),
        logger: Optional[logging.Logger] = None,
        log_queue: Optional[multiprocessing.Queue[Any]] = None,
        log_level: int = logging.INFO,
    ):
        self._logger = logger or logging.getLogger("stt.process")
        self._worker = _DedicatedProcessWorker(
            name="stt-worker",
            target=_stt_worker_main,
            target_args=(config, cpu_cores),
            logger=self._logger,
            log_queue=log_queue,
            log_level=log_level,
        )

    def transcribe(self, utterance: "Utterance") -> "TranscriptionResult":
        from stt import STTError

        try:
            return self._worker.call(utterance)
        except Exception as error:
            raise STTError(f"Process STT failed: {error}") from error

    def close(self, timeout_seconds: float = 5.0) -> None:
        self._worker.close(timeout_seconds=timeout_seconds)


class ProcessLLMClient:
    """Process-backed LLM client compatible with `PomodoroAssistantLLM.run`."""

    def __init__(
        self,
        *,
        config: "LLMConfig",
        cpu_cores: tuple[int, ...] = (),
        logger: Optional[logging.Logger] = None,
        log_queue: Optional[multiprocessing.Queue[Any]] = None,
        log_level: int = logging.INFO,
    ):
        self._logger = logger or logging.getLogger("llm.process")
        self._worker = _DedicatedProcessWorker(
            name="llm-worker",
            target=_llm_worker_main,
            target_args=(config, cpu_cores),
            logger=self._logger,
            log_queue=log_queue,
            log_level=log_level,
        )

    def run(
        self,
        user_prompt: str,
        *,
        env: Optional["EnvironmentContext"] = None,
        extra_context: Optional[str] = None,
        max_tokens: int = 256,
    ) -> "StructuredResponse":
        payload = {
            "user_prompt": user_prompt,
            "env": env,
            "extra_context": extra_context,
            "max_tokens": max_tokens,
        }
        return self._worker.call(payload)

    def close(self, timeout_seconds: float = 5.0) -> None:
        self._worker.close(timeout_seconds=timeout_seconds)


class ProcessTTSClient:
    """Process-backed TTS client compatible with `SpeechService.speak`."""

    def __init__(
        self,
        *,
        config: "TTSConfig",
        cpu_cores: tuple[int, ...] = (),
        logger: Optional[logging.Logger] = None,
        log_queue: Optional[multiprocessing.Queue[Any]] = None,
        log_level: int = logging.INFO,
    ):
        self._logger = logger or logging.getLogger("tts.process")
        self._worker = _DedicatedProcessWorker(
            name="tts-worker",
            target=_tts_worker_main,
            target_args=(config, cpu_cores),
            logger=self._logger,
            log_queue=log_queue,
            log_level=log_level,
        )

    def speak(self, text: str) -> None:
        from tts import TTSError

        try:
            self._worker.call(text)
        except Exception as error:
            raise TTSError(f"Process TTS failed: {error}") from error

    def close(self, timeout_seconds: float = 5.0) -> None:
        self._worker.close(timeout_seconds=timeout_seconds)


def _stt_worker_main(
    request_queue: multiprocessing.Queue[Any],
    response_queue: multiprocessing.Queue[Any],
    log_queue: Optional[multiprocessing.Queue[Any]],
    log_level: int,
    config: "STTConfig",
    cpu_cores: tuple[int, ...],
) -> None:
    _configure_worker_logging(log_queue=log_queue, log_level=log_level)
    logger = logging.getLogger("stt.worker")
    _set_process_cpu_affinity(cpu_cores, logger=logger)

    try:
        from stt import FasterWhisperSTT

        stt = FasterWhisperSTT(
            model_size=config.model_size,
            device=config.device,
            compute_type=config.compute_type,
            language=config.language,
            beam_size=config.beam_size,
            vad_filter=config.vad_filter,
            logger=logger,
        )
        response_queue.put((_READY, None))
    except Exception as error:
        response_queue.put((_INIT_ERROR, str(error)))
        return

    while True:
        payload = request_queue.get()
        if payload == _SHUTDOWN:
            return
        try:
            response_queue.put((_OK, stt.transcribe(payload)))
        except Exception as error:
            response_queue.put((_ERROR, f"{type(error).__name__}: {error}"))


def _llm_worker_main(
    request_queue: multiprocessing.Queue[Any],
    response_queue: multiprocessing.Queue[Any],
    log_queue: Optional[multiprocessing.Queue[Any]],
    log_level: int,
    config: "LLMConfig",
    cpu_cores: tuple[int, ...],
) -> None:
    from dataclasses import replace

    _configure_worker_logging(log_queue=log_queue, log_level=log_level)
    logger = logging.getLogger("llm.worker")
    _set_process_cpu_affinity(cpu_cores, logger=logger)

    llm_config = config
    if cpu_cores and llm_config.n_threads > len(cpu_cores):
        llm_config = replace(llm_config, n_threads=len(cpu_cores))
        logger.info("Adjusted llm.n_threads to %d to match assigned CPU cores", len(cpu_cores))

    try:
        from llm import PomodoroAssistantLLM

        assistant = PomodoroAssistantLLM(llm_config)
        response_queue.put((_READY, None))
    except Exception as error:
        response_queue.put((_INIT_ERROR, str(error)))
        return

    while True:
        payload = request_queue.get()
        if payload == _SHUTDOWN:
            return
        try:
            response_queue.put(
                (
                    _OK,
                    assistant.run(
                        payload["user_prompt"],
                        env=payload.get("env"),
                        extra_context=payload.get("extra_context"),
                        max_tokens=payload.get("max_tokens", 256),
                    ),
                )
            )
        except Exception as error:
            response_queue.put((_ERROR, f"{type(error).__name__}: {error}"))


def _tts_worker_main(
    request_queue: multiprocessing.Queue[Any],
    response_queue: multiprocessing.Queue[Any],
    log_queue: Optional[multiprocessing.Queue[Any]],
    log_level: int,
    config: "TTSConfig",
    cpu_cores: tuple[int, ...],
) -> None:
    _configure_worker_logging(log_queue=log_queue, log_level=log_level)
    logger = logging.getLogger("tts.worker")
    _set_process_cpu_affinity(cpu_cores, logger=logger)

    try:
        from tts import PiperTTSEngine, SoundDeviceAudioOutput, SpeechService

        engine = PiperTTSEngine(config=config, logger=logger.getChild("engine"))
        output = SoundDeviceAudioOutput(
            output_device_index=config.output_device_index,
            logger=logger.getChild("output"),
        )
        speech_service = SpeechService(
            engine=engine,
            output=output,
            logger=logger,
        )
        response_queue.put((_READY, None))
    except Exception as error:
        response_queue.put((_INIT_ERROR, str(error)))
        return

    while True:
        payload = request_queue.get()
        if payload == _SHUTDOWN:
            return
        try:
            speech_service.speak(payload)
            response_queue.put((_OK, None))
        except Exception as error:
            response_queue.put((_ERROR, f"{type(error).__name__}: {error}"))

from __future__ import annotations

import logging
from dataclasses import dataclass
from multiprocessing.queues import Queue as MPQueue
from typing import TYPE_CHECKING, cast

from contracts import StartupError
from stt.config import ConfigurationError
from stt.factory import create_stt_resources

from .core import _ProcessWorker, WorkerInitError

if TYPE_CHECKING:
    from stt.config import STTConfig, WakeWordConfig
    from stt.events import Utterance
    from stt.transcription import TranscriptionResult


@dataclass(frozen=True, slots=True)
class _WorkerConfig:
    stt_config: "STTConfig"


class _STTProcess:
    def __init__(self, config: "STTConfig") -> None:
        from stt.transcription import FasterWhisperSTT

        self._stt = FasterWhisperSTT(
            model_size=config.model_size,
            device=config.device,
            compute_type=config.compute_type,
            language=config.language,
            beam_size=config.beam_size,
            vad_filter=config.vad_filter,
            cpu_threads=config.cpu_threads,
            logger=logging.getLogger("stt.worker"),
        )

    def handle(self, payload: object) -> object:
        from stt.events import Utterance

        if not isinstance(payload, Utterance):
            raise ValueError(f"Expected Utterance payload, got {type(payload).__name__}")
        return self._stt.transcribe(payload)


def _create_stt_process(worker_config: _WorkerConfig) -> _STTProcess:
    return _STTProcess(worker_config.stt_config)


class STTWorker:
    def __init__(
        self,
        *,
        config: "STTConfig",
        cpu_cores: tuple[int, ...] = (),
        logger: logging.Logger | None = None,
        log_queue: MPQueue | None = None,
        log_level: int = logging.INFO,
    ):
        worker_logger = logger or logging.getLogger("stt.process")
        worker_config = _WorkerConfig(stt_config=config)
        self._worker = _ProcessWorker(
            name="stt-worker",
            runtime_factory=_create_stt_process,
            runtime_args=(worker_config,),
            cpu_cores=tuple(cpu_cores),
            log_queue=log_queue,
            log_level=log_level,
            logger=worker_logger,
        )

    def transcribe(self, utterance: "Utterance") -> "TranscriptionResult":
        from stt.transcription import STTError

        try:
            result = self._worker.call(utterance)
            return cast("TranscriptionResult", result)
        except Exception as error:
            raise STTError(f"Process STT failed: {error}") from error

    def close(self, timeout_seconds: float = 5.0) -> None:
        self._worker.close(timeout_seconds=timeout_seconds)

    def __enter__(self) -> STTWorker:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def create_stt_worker(
    *,
    wake_word,
    stt,
    pico_key: str,
    log_queue: MPQueue,
    log_level: int,
    logger: logging.Logger | None = None,
) -> tuple["WakeWordConfig", STTWorker]:
    try:
        wake_word_config, stt_config = create_stt_resources(
            wake_word=wake_word,
            stt=stt,
            pico_key=pico_key,
        )
        stt_worker = STTWorker(
            config=stt_config,
            cpu_cores=tuple(stt.cpu_cores),
            logger=logger or logging.getLogger("stt.process"),
            log_queue=log_queue,
            log_level=log_level,
        )
        return wake_word_config, stt_worker
    except ConfigurationError as error:
        raise StartupError(f"STT configuration error: {error}") from error
    except ImportError as error:
        raise StartupError(f"STT module import error: {error}") from error
    except WorkerInitError as error:
        raise StartupError(f"STT initialization failed: {type(error).__name__}: {error}") from error
    except Exception as error:
        raise StartupError(
            f"STT initialization failed: {type(error).__name__}: {error}"
        ) from error

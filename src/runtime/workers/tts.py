from __future__ import annotations

import logging
from dataclasses import dataclass
from multiprocessing.queues import Queue as MPQueue
from typing import TYPE_CHECKING

from contracts import StartupError
from tts.config import TTSConfigurationError
from tts.factory import create_tts_config

from .core import _ProcessWorker, WorkerInitError

if TYPE_CHECKING:
    from tts.config import TTSConfig


@dataclass(frozen=True, slots=True)
class TTSPayload:
    text: str


@dataclass(frozen=True, slots=True)
class _WorkerConfig:
    tts_config: "TTSConfig"


class _TTSProcess:
    def __init__(self, config: "TTSConfig") -> None:
        from tts.engine import PiperTTSEngine
        from tts.output import SoundDeviceAudioOutput
        from tts.service import SpeechService

        logger = logging.getLogger("tts.worker")
        self._speech_service = SpeechService(
            engine=PiperTTSEngine(config=config, logger=logger.getChild("engine")),
            output=SoundDeviceAudioOutput(
                output_device_index=config.output_device_index,
                logger=logger.getChild("output"),
            ),
            logger=logger,
        )

    def handle(self, payload: object) -> object:
        if not isinstance(payload, TTSPayload):
            raise ValueError(f"Expected TTSPayload, got {type(payload).__name__}")
        self._speech_service.speak(payload.text)
        return None


def _create_tts_process(worker_config: _WorkerConfig) -> _TTSProcess:
    return _TTSProcess(worker_config.tts_config)


class TTSWorker:
    def __init__(
        self,
        *,
        config: "TTSConfig",
        cpu_cores: tuple[int, ...] = (),
        logger: logging.Logger | None = None,
        log_queue: MPQueue | None = None,
        log_level: int = logging.INFO,
    ):
        worker_logger = logger or logging.getLogger("tts.process")
        worker_config = _WorkerConfig(tts_config=config)
        self._worker = _ProcessWorker(
            name="tts-worker",
            runtime_factory=_create_tts_process,
            runtime_args=(worker_config,),
            cpu_cores=tuple(cpu_cores),
            log_queue=log_queue,
            log_level=log_level,
            logger=worker_logger,
        )

    def speak(self, text: str) -> None:
        from tts.engine import TTSError

        try:
            self._worker.call(TTSPayload(text=text))
        except Exception as error:
            raise TTSError(f"Process TTS failed: {error}") from error

    def close(self, timeout_seconds: float = 5.0) -> None:
        self._worker.close(timeout_seconds=timeout_seconds)

    def __enter__(self) -> TTSWorker:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def create_tts_worker(
    *,
    tts,
    log_queue: MPQueue,
    log_level: int,
    logger: logging.Logger | None = None,
) -> TTSWorker | None:
    if not tts.enabled:
        return None

    try:
        tts_config = create_tts_config(tts=tts)
        return TTSWorker(
            config=tts_config,
            cpu_cores=tuple(tts.cpu_cores),
            logger=logger or logging.getLogger("tts.process"),
            log_queue=log_queue,
            log_level=log_level,
        )
    except TTSConfigurationError as error:
        raise StartupError(f"TTS configuration error: {error}") from error
    except ImportError as error:
        raise StartupError(f"TTS module import error: {error}") from error
    except WorkerInitError as error:
        raise StartupError(f"TTS initialization failed: {type(error).__name__}: {error}") from error
    except Exception as error:
        raise StartupError(
            f"TTS initialization failed: {type(error).__name__}: {error}"
        ) from error

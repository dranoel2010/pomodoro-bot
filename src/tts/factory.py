from __future__ import annotations

import logging
from multiprocessing.queues import Queue as MPQueue

from contracts import StartupError

from .config import TTSConfig, TTSConfigurationError


def create_tts_client(*, tts, log_queue: MPQueue, log_level: int):
    if not tts.enabled:
        return None

    try:
        from runtime.process_workers import ProcessTTSClient

        return ProcessTTSClient(
            config=TTSConfig.from_settings(tts),
            cpu_cores=tts.cpu_cores,
            logger=logging.getLogger("tts.process"),
            log_queue=log_queue,
            log_level=log_level,
        )
    except TTSConfigurationError as error:
        raise StartupError(f"TTS configuration error: {error}")
    except ImportError as error:
        raise StartupError(f"TTS module import error: {error}")
    except Exception as error:
        raise StartupError(f"TTS initialization failed: {type(error).__name__}: {error}")

from __future__ import annotations

import logging
from multiprocessing.queues import Queue as MPQueue

from contracts import StartupError

from .config import ConfigurationError, STTConfig, WakeWordConfig


def create_stt_client(*, wake_word, stt, pico_key: str, log_queue: MPQueue, log_level: int):
    try:
        from runtime.process_workers import ProcessSTTClient

        wake_word_config = WakeWordConfig.from_settings(
            pico_voice_access_key=pico_key,
            settings=wake_word,
        )
        stt_config = STTConfig.from_settings(stt)
        stt_client = ProcessSTTClient(
            config=stt_config,
            cpu_cores=stt.cpu_cores,
            logger=logging.getLogger("stt.process"),
            log_queue=log_queue,
            log_level=log_level,
        )
    except ConfigurationError as error:
        raise StartupError(f"STT configuration error: {error}")
    except ImportError as error:
        raise StartupError(f"STT module import error: {error}")
    except Exception as error:
        raise StartupError(f"STT initialization failed: {type(error).__name__}: {error}")

    return wake_word_config, stt_client

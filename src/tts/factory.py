"""Startup factory for process-backed text-to-speech client construction."""

from __future__ import annotations

import logging
from multiprocessing.queues import Queue as MPQueue
from typing import TYPE_CHECKING

from contracts.errors import StartupError

from .config import TTSConfig, TTSConfigurationError

if TYPE_CHECKING:
    from app_config import TTSSettings
    from runtime.process_workers import ProcessTTSClient


def create_tts_client(
    *,
    tts: "TTSSettings",
    log_queue: MPQueue,
    log_level: int,
) -> "ProcessTTSClient" | None:
    """Build process-backed TTS client when the feature is enabled."""

    if not tts.enabled:
        return None

    try:
        from runtime.process_workers import ProcessTTSClient
    except ImportError as error:
        raise StartupError(f"TTS module import error: {error}")

    try:
        tts_config = TTSConfig.from_settings(tts)
    except TTSConfigurationError as error:
        raise StartupError(f"TTS configuration error: {error}")

    try:
        return ProcessTTSClient(
            config=tts_config,
            cpu_cores=tts.cpu_cores,
            logger=logging.getLogger("tts.process"),
            log_queue=log_queue,
            log_level=log_level,
        )
    except Exception as error:
        raise StartupError(
            f"TTS initialization failed: {type(error).__name__}: {error}"
        )

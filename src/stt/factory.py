"""Startup factory for wake-word/STT process client construction."""

from __future__ import annotations

import logging
from multiprocessing.queues import Queue as MPQueue
from typing import TYPE_CHECKING

from contracts.errors import StartupError

from .config import ConfigurationError, STTConfig, WakeWordConfig

if TYPE_CHECKING:
    from app_config import STTSettings, WakeWordSettings
    from runtime.process_workers import ProcessSTTClient


def create_stt_client(
    *,
    wake_word: "WakeWordSettings",
    stt: "STTSettings",
    pico_key: str,
    log_queue: MPQueue,
    log_level: int,
) -> tuple[WakeWordConfig, "ProcessSTTClient"]:
    """Build wake-word config plus process-backed STT client for runtime startup."""

    try:
        from runtime.process_workers import ProcessSTTClient
    except ImportError as error:
        raise StartupError(f"STT module import error: {error}")

    try:
        wake_word_config = WakeWordConfig.from_settings(
            pico_voice_access_key=pico_key,
            settings=wake_word,
        )
        stt_config = STTConfig.from_settings(stt)
    except ConfigurationError as error:
        raise StartupError(f"STT configuration error: {error}")

    try:
        stt_client = ProcessSTTClient(
            config=stt_config,
            cpu_cores=stt.cpu_cores,
            logger=logging.getLogger("stt.process"),
            log_queue=log_queue,
            log_level=log_level,
        )
    except Exception as error:
        raise StartupError(
            f"STT initialization failed: {type(error).__name__}: {error}"
        )

    return wake_word_config, stt_client

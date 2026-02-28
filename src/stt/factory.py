from __future__ import annotations

from .config import STTConfig, WakeWordConfig


def create_stt_resources(*, wake_word, stt, pico_key: str) -> tuple[WakeWordConfig, STTConfig]:
    wake_word_config = WakeWordConfig.from_settings(
        pico_voice_access_key=pico_key,
        settings=wake_word,
    )
    stt_config = STTConfig.from_settings(stt)
    return wake_word_config, stt_config

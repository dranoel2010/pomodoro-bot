from __future__ import annotations

from .config import TTSConfig


def create_tts_config(*, tts) -> TTSConfig:
    return TTSConfig.from_settings(tts)

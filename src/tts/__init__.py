"""TTS package exports."""

__all__ = ["SpeechService", "TTSConfig"]


def __getattr__(name: str):
    if name == "SpeechService":
        from .service import SpeechService

        return SpeechService
    if name == "TTSConfig":
        from .config import TTSConfig

        return TTSConfig
    raise AttributeError(name)

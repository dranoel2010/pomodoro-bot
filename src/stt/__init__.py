"""STT package exports."""

__all__ = ["FasterWhisperSTT", "STTConfig", "WakeWordConfig", "WakeWordService"]


def __getattr__(name: str):
    if name == "FasterWhisperSTT":
        from .stt import FasterWhisperSTT

        return FasterWhisperSTT
    if name == "STTConfig":
        from .config import STTConfig

        return STTConfig
    if name == "WakeWordConfig":
        from .config import WakeWordConfig

        return WakeWordConfig
    if name == "WakeWordService":
        from .service import WakeWordService

        return WakeWordService
    raise AttributeError(name)

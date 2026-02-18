from dataclasses import dataclass
from typing import Optional

from stt import ConfigurationError


@dataclass(frozen=True)
class TTSConfig:
    model_path: str = ""
    config_path: str = ""
    gpu: bool = False
    output_device_index: Optional[int] = None

    @classmethod
    def from_settings(cls, settings) -> "TTSConfig":
        model_path = settings.model_path
        config_path = settings.config_path

        if not model_path:
            raise ConfigurationError("TTS model_path cannot be empty")
        if not config_path:
            raise ConfigurationError("TTS config_path cannot be empty")

        return cls(
            model_path=model_path,
            config_path=config_path,
            gpu=bool(settings.gpu),
            output_device_index=settings.output_device,
        )

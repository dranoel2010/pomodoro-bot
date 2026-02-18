import os
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
    def from_environment(cls) -> "TTSConfig":
        model_path = os.getenv("TTS_MODEL_PATH", "")
        config_path = os.getenv("TTS_CONFIG_PATH", "")
        gpu = os.getenv("TTS_GPU", "false").lower() == "true"

        output_device_index = None
        raw_device = os.getenv("TTS_OUTPUT_DEVICE")
        if raw_device:
            try:
                output_device_index = int(raw_device)
            except ValueError as error:
                raise ConfigurationError(
                    f"TTS_OUTPUT_DEVICE must be an integer, got: {raw_device}"
                ) from error

        if not model_path:
            raise ConfigurationError("TTS_MODEL_PATH cannot be empty")
        if not config_path:
            raise ConfigurationError("TTS_CONFIG_PATH cannot be empty")

        return cls(
            model_path=model_path,
            config_path=config_path,
            gpu=gpu,
            output_device_index=output_device_index,
        )

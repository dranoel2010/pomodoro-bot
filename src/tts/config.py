"""Configuration model for Piper-based TTS assets and output selection."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class TTSConfigurationError(Exception):
    """Raised when TTS configuration is invalid."""


@dataclass(frozen=True)
class TTSConfig:
    """Resolved Piper model settings and optional output-device selection."""
    model_path: str = ""
    hf_filename: str = ""
    hf_repo_id: str = ""
    hf_revision: str = "main"
    output_device_index: Optional[int] = None

    @classmethod
    def from_settings(cls, settings) -> "TTSConfig":
        model_path = (settings.model_path or "").strip()
        hf_filename = (getattr(settings, "hf_filename", "") or "").strip()
        hf_repo_id = (getattr(settings, "hf_repo_id", "") or "").strip()
        hf_revision = (getattr(settings, "hf_revision", "main") or "main").strip()

        if not model_path:
            raise TTSConfigurationError("TTS model_path cannot be empty")
        if not hf_filename:
            # Backward-compatible fallback: allow model_path to directly reference .onnx.
            model_path_file = Path(model_path)
            if model_path_file.suffix.lower() != ".onnx":
                raise TTSConfigurationError("TTS hf_filename cannot be empty")
            hf_filename = model_path_file.name
            model_path = str(model_path_file.parent)

        return cls(
            model_path=model_path,
            hf_filename=hf_filename,
            hf_repo_id=hf_repo_id,
            hf_revision=hf_revision,
            output_device_index=settings.output_device,
        )

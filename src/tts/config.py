"""Configuration model for Piper-based TTS assets and output selection."""

from dataclasses import dataclass
from typing import Self


class TTSConfigurationError(Exception):
    """Raised when TTS configuration is invalid."""


@dataclass(frozen=True, slots=True)
class TTSConfig:
    """Resolved Piper model settings and optional output-device selection."""
    model_path: str = ""
    hf_filename: str = ""
    hf_repo_id: str = ""
    hf_revision: str = "main"
    output_device_index: int | None = None

    @classmethod
    def from_settings(cls, settings) -> Self:
        model_path = (settings.model_path or "").strip()
        hf_filename = (getattr(settings, "hf_filename", "") or "").strip()
        hf_repo_id = (getattr(settings, "hf_repo_id", "") or "").strip()
        hf_revision = (getattr(settings, "hf_revision", "main") or "main").strip()

        if not model_path:
            raise TTSConfigurationError("TTS model_path cannot be empty")
        if not hf_filename:
            raise TTSConfigurationError("TTS hf_filename cannot be empty")

        return cls(
            model_path=model_path,
            hf_filename=hf_filename,
            hf_repo_id=hf_repo_id,
            hf_revision=hf_revision,
            output_device_index=settings.output_device,
        )

import logging
import os
from typing import Optional

import numpy as np
from huggingface_hub import snapshot_download

from .config import TTSConfig


class TTSError(Exception):
    """Raised when text-to-speech processing fails."""

    pass


class CoquiTTSEngine:
    def __init__(
        self,
        config: TTSConfig,
        logger: Optional[logging.Logger] = None,
    ):
        self._config = config
        self._logger = logger or logging.getLogger(__name__)
        model_path, config_path = self._ensure_model_files()

        try:
            from TTS.api import TTS

            self._tts = TTS(
                model_path=model_path,
                config_path=config_path,
                gpu=self._config.gpu,
                progress_bar=False,
            )
        except Exception as error:
            raise TTSError(f"Failed to initialize TTS engine: {error}") from error

    def _ensure_model_files(self) -> tuple[str, str]:
        model_path = self._config.model_path
        config_path = self._config.config_path

        if os.path.exists(model_path) and os.path.exists(config_path):
            return model_path, config_path

        repo_id = os.getenv("TTS_HF_REPO_ID", "")
        local_dir = os.getenv("TTS_HF_LOCAL_DIR", "")
        if not (repo_id or filename):
            raise ValueError(
                "LLM is missing configuration. Set either TTS_HF_LOCAL_DIR to an existing model "
                "file, or set TTS_HF_REPO_ID to auto-download."
            )

        self._logger.info(
            "TTS model files not found locally, downloading from %s into %s",
            repo_id,
            local_dir,
        )
        try:
            snapshot_download(
                repo_id=repo_id,
                local_dir=local_dir,
                local_dir_use_symlinks=False,
            )
        except Exception as error:
            raise TTSError(
                f"Failed to download TTS model from Hugging Face: {error}"
            ) from error

        resolved_model_path = os.path.join(local_dir, "model_file.pth")
        resolved_config_path = os.path.join(local_dir, "config.json")
        if not os.path.exists(resolved_model_path) or not os.path.exists(
            resolved_config_path
        ):
            raise TTSError(
                "Downloaded TTS assets are incomplete. "
                "Expected model_file.pth and config.json in local model directory."
            )

        return resolved_model_path, resolved_config_path

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        if not text.strip():
            raise TTSError("Text to synthesize cannot be empty")

        try:
            wav = np.asarray(self._tts.tts(text), dtype=np.float32)
            sample_rate_hz = self._tts.synthesizer.output_sample_rate
            return wav, sample_rate_hz
        except Exception as error:
            raise TTSError(f"TTS synthesis failed: {error}") from error

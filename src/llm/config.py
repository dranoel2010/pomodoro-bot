from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .model_store import HFModelSpec, ModelDownloadError, ensure_model_downloaded


class ConfigurationError(Exception):
    """Raised when configuration is invalid."""

    pass


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for LLM inference."""

    model_path: str
    n_threads: int = 4
    n_ctx: int = 2048
    n_batch: int = 256
    temperature: float = 0.2
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    verbose: bool = False

    def __post_init__(self):
        """Validate configuration values."""
        # Validate model path
        if not self.model_path or not self.model_path.strip():
            raise ConfigurationError("model_path cannot be empty")

        model_file = Path(self.model_path)
        if not model_file.exists():
            raise ConfigurationError(f"Model file does not exist: {self.model_path}")
        if not model_file.is_file():
            raise ConfigurationError(f"Model path is not a file: {self.model_path}")

        # Validate numeric ranges
        if self.n_threads < 1:
            raise ConfigurationError(f"n_threads must be >= 1, got: {self.n_threads}")
        if self.n_threads > 64:
            raise ConfigurationError(
                f"n_threads too high ({self.n_threads}), consider <= 64"
            )

        if self.n_ctx < 128:
            raise ConfigurationError(f"n_ctx must be >= 128, got: {self.n_ctx}")
        if self.n_ctx > 32768:
            raise ConfigurationError(
                f"n_ctx too high ({self.n_ctx}), consider <= 32768"
            )

        if self.n_batch < 1:
            raise ConfigurationError(f"n_batch must be >= 1, got: {self.n_batch}")
        if self.n_batch > self.n_ctx:
            raise ConfigurationError(
                f"n_batch ({self.n_batch}) cannot exceed n_ctx ({self.n_ctx})"
            )

        if not 0.0 <= self.temperature <= 2.0:
            raise ConfigurationError(
                f"temperature must be in [0.0, 2.0], got: {self.temperature}"
            )

        if not 0.0 <= self.top_p <= 1.0:
            raise ConfigurationError(f"top_p must be in [0.0, 1.0], got: {self.top_p}")

        if not 1.0 <= self.repeat_penalty <= 2.0:
            raise ConfigurationError(
                f"repeat_penalty must be in [1.0, 2.0], got: {self.repeat_penalty}"
            )

    @classmethod
    def from_environment(
        cls,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> "LLMConfig":
        """Load configuration from environment variables.

        Required environment variables:
            - LLM_MODEL_PATH: Directory to store model files
            - LLM_HF_FILENAME: Model filename (e.g., "model.gguf")
            - LLM_HF_REPO_ID: Hugging Face repo (if model needs downloading)

        Optional environment variables:
            - LLM_HF_REVISION: Git revision/tag (default: main)
            - HF_TOKEN: Hugging Face API token
            - LLM_N_THREADS: Number of CPU threads (default: 4)
            - LLM_N_CTX: Context window size (default: 2048)
            - LLM_N_BATCH: Batch size (default: 256)
            - LLM_TEMPERATURE: Sampling temperature (default: 0.2)
            - LLM_TOP_P: Nucleus sampling (default: 0.9)
            - LLM_REPEAT_PENALTY: Repetition penalty (default: 1.1)
            - LLM_VERBOSE: Enable verbose output (default: false)

        Args:
            logger: Optional logger for diagnostics

        Returns:
            Validated LLMConfig instance

        Raises:
            ConfigurationError: If configuration is invalid or incomplete
        """
        logger = logger or logging.getLogger(__name__)

        try:
            model_path = cls._resolve_model_path(logger=logger)
        except (ValueError, ModelDownloadError) as e:
            raise ConfigurationError(f"Failed to resolve model path: {e}") from e

        # Parse numeric values with error handling
        try:
            n_threads = int(os.getenv("LLM_N_THREADS", "4"))
        except ValueError as e:
            raise ConfigurationError(
                f"LLM_N_THREADS must be an integer, got: {os.getenv('LLM_N_THREADS')}"
            ) from e

        try:
            n_ctx = int(os.getenv("LLM_N_CTX", "2048"))
        except ValueError as e:
            raise ConfigurationError(
                f"LLM_N_CTX must be an integer, got: {os.getenv('LLM_N_CTX')}"
            ) from e

        try:
            n_batch = int(os.getenv("LLM_N_BATCH", "256"))
        except ValueError as e:
            raise ConfigurationError(
                f"LLM_N_BATCH must be an integer, got: {os.getenv('LLM_N_BATCH')}"
            ) from e

        try:
            temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        except ValueError as e:
            raise ConfigurationError(
                f"LLM_TEMPERATURE must be a number, got: {os.getenv('LLM_TEMPERATURE')}"
            ) from e

        try:
            top_p = float(os.getenv("LLM_TOP_P", "0.9"))
        except ValueError as e:
            raise ConfigurationError(
                f"LLM_TOP_P must be a number, got: {os.getenv('LLM_TOP_P')}"
            ) from e

        try:
            repeat_penalty = float(os.getenv("LLM_REPEAT_PENALTY", "1.1"))
        except ValueError as e:
            raise ConfigurationError(
                f"LLM_REPEAT_PENALTY must be a number, got: {os.getenv('LLM_REPEAT_PENALTY')}"
            ) from e

        verbose = os.getenv("LLM_VERBOSE", "false").lower() in ("true", "1", "yes")

        return cls(
            model_path=model_path,
            n_threads=n_threads,
            n_ctx=n_ctx,
            n_batch=n_batch,
            temperature=temperature,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
            verbose=verbose,
        )

    @staticmethod
    def _resolve_model_path(
        *,
        logger: Optional[logging.Logger] = None,
    ) -> str:
        """Resolve model path, downloading from HF if necessary.

        Args:
            logger: Optional logger for diagnostics

        Returns:
            Absolute path to validated model file

        Raises:
            ConfigurationError: If required env vars missing
            ModelDownloadError: If download fails
        """
        logger = logger or logging.getLogger(__name__)

        # Get required variables
        model_dir_str = os.getenv("LLM_MODEL_PATH", "").strip()
        if not model_dir_str:
            raise ConfigurationError(
                "LLM_MODEL_PATH is required and must point to a directory"
            )

        filename = os.getenv("LLM_HF_FILENAME", "").strip()
        if not filename:
            raise ConfigurationError("LLM_HF_FILENAME is required")

        if not filename.endswith(".gguf"):
            raise ConfigurationError(
                f"LLM_HF_FILENAME must be a .gguf file, got: {filename}"
            )

        # Validate model directory
        model_dir = Path(model_dir_str)

        # Get HF download parameters
        repo_id = os.getenv("LLM_HF_REPO_ID", "").strip() or None
        revision = os.getenv("LLM_HF_REVISION", "").strip() or None
        hf_token = os.getenv("HF_TOKEN", "").strip() or None

        # If no repo_id, expect file to already exist
        if not repo_id:
            target_path = model_dir / filename
            if not target_path.exists():
                raise ConfigurationError(
                    f"Model file not found: {target_path}\n"
                    f"Either place the file there manually or set LLM_HF_REPO_ID "
                    f"to download it automatically."
                )
            if not target_path.is_file():
                raise ConfigurationError(
                    f"Model path exists but is not a file: {target_path}"
                )

            logger.info(f"Using existing model: {target_path}")
            return str(target_path.absolute())

        # Download/validate model using model_store
        logger.info(f"Ensuring model is available: {repo_id}/{filename}")

        spec = HFModelSpec(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
        )

        try:
            resolved_path = ensure_model_downloaded(
                spec,
                models_dir=model_dir,
                hf_token=hf_token,
                logger=logger,
            )
            return str(resolved_path.absolute())
        except ModelDownloadError as e:
            raise ConfigurationError(
                f"Failed to download model from {repo_id}: {e}"
            ) from e

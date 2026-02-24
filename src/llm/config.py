"""Validation and resolution helpers for LLM runtime configuration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from .model_store import HFModelSpec, ModelDownloadError, ensure_model_downloaded


class ConfigurationError(Exception):
    """Raised when configuration is invalid."""

    pass


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Configuration for LLM inference."""

    model_path: str
    system_prompt_path: str | None = None
    max_tokens: int = 256
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

        if self.max_tokens < 1:
            raise ConfigurationError(
                f"max_tokens must be >= 1, got: {self.max_tokens}"
            )
        if self.max_tokens > self.n_ctx:
            raise ConfigurationError(
                f"max_tokens ({self.max_tokens}) cannot exceed n_ctx ({self.n_ctx})"
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
    def from_sources(
        cls,
        *,
        model_dir: str,
        hf_filename: str,
        hf_repo_id: str | None = None,
        hf_revision: str | None = None,
        hf_token: str | None = None,
        system_prompt_path: str | None = None,
        max_tokens: int | None = None,
        n_threads: int | None = None,
        n_ctx: int | None = None,
        n_batch: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        repeat_penalty: float | None = None,
        verbose: bool | None = None,
        logger: logging.Logger | None = None,
    ) -> Self:
        logger = logger or logging.getLogger(__name__)
        try:
            model_path = cls._resolve_model_path_from_values(
                model_dir=model_dir,
                filename=hf_filename,
                repo_id=hf_repo_id,
                revision=hf_revision,
                hf_token=hf_token,
                logger=logger,
            )
        except (ValueError, ModelDownloadError) as e:
            raise ConfigurationError(f"Failed to resolve model path: {e}") from e

        config_kwargs: dict[str, object] = {
            "model_path": model_path,
            "system_prompt_path": (system_prompt_path or "").strip() or None,
        }
        if max_tokens is not None:
            config_kwargs["max_tokens"] = max_tokens
        if n_threads is not None:
            config_kwargs["n_threads"] = n_threads
        if n_ctx is not None:
            config_kwargs["n_ctx"] = n_ctx
        if n_batch is not None:
            config_kwargs["n_batch"] = n_batch
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if top_p is not None:
            config_kwargs["top_p"] = top_p
        if repeat_penalty is not None:
            config_kwargs["repeat_penalty"] = repeat_penalty
        if verbose is not None:
            config_kwargs["verbose"] = verbose
        return cls(**config_kwargs)

    @staticmethod
    def _resolve_model_path_from_values(
        *,
        model_dir: str,
        filename: str,
        repo_id: str | None,
        revision: str | None,
        hf_token: str | None,
        logger: logging.Logger | None = None,
    ) -> str:
        logger = logger or logging.getLogger(__name__)

        model_dir_str = model_dir.strip()
        if not model_dir_str:
            raise ConfigurationError(
                "model_dir is required and must point to a directory"
            )

        filename = filename.strip()
        if not filename:
            raise ConfigurationError("hf_filename is required")

        if not filename.endswith(".gguf"):
            raise ConfigurationError(
                f"hf_filename must be a .gguf file, got: {filename}"
            )

        model_dir_path = Path(model_dir_str)

        if not repo_id:
            target_path = model_dir_path / filename
            if not target_path.exists():
                raise ConfigurationError(
                    f"Model file not found: {target_path}\n"
                    f"Either place the file there manually or set hf_repo_id "
                    f"to download it automatically."
                )
            if not target_path.is_file():
                raise ConfigurationError(
                    f"Model path exists but is not a file: {target_path}"
                )

            logger.info(f"Using existing model: {target_path}")
            return str(target_path.absolute())

        logger.info(f"Ensuring model is available: {repo_id}/{filename}")
        spec = HFModelSpec(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
        )

        try:
            resolved_path = ensure_model_downloaded(
                spec,
                models_dir=model_dir_path,
                hf_token=hf_token,
                logger=logger,
            )
            return str(resolved_path.absolute())
        except ModelDownloadError as e:
            raise ConfigurationError(
                f"Failed to download model from {repo_id}: {e}"
            ) from e

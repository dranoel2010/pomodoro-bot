"""Hugging Face download and GGUF validation helpers for local models."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from huggingface_hub import hf_hub_download
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError


class ModelDownloadError(Exception):
    """Raised when model download or validation fails."""

    pass


@dataclass(frozen=True)
class HFModelSpec:
    """Specification for a Hugging Face model file."""

    repo_id: str
    filename: str
    revision: Optional[str] = None

    def __post_init__(self):
        """Validate spec fields."""
        if not self.repo_id or not self.repo_id.strip():
            raise ValueError("repo_id cannot be empty")
        if not self.filename or not self.filename.strip():
            raise ValueError("filename cannot be empty")
        if not self.filename.endswith(".gguf"):
            raise ValueError(f"filename must be a .gguf file, got: {self.filename}")


def _validate_gguf_file(path: Path, logger: logging.Logger) -> bool:
    """Validate that file is a GGUF format.

    Checks magic bytes at start of file.
    """
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            # GGUF magic: 'GGUF' or 0x46554747
            if magic == b"GGUF":
                return True
            logger.warning(f"File {path} does not have GGUF magic bytes: {magic.hex()}")
            return False
    except Exception as e:
        logger.error(f"Failed to validate GGUF file: {e}")
        return False


def ensure_model_downloaded(
    spec: HFModelSpec,
    *,
    models_dir: str | Path = "models",
    hf_token: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    validate_gguf: bool = True,
) -> Path:
    """Ensure the exact GGUF model file exists locally and return its path.

    Args:
        spec: Model specification (repo, filename, revision)
        models_dir: Local directory to store models
        hf_token: Optional Hugging Face API token
        logger: Optional logger for diagnostics
        validate_gguf: Whether to validate GGUF magic bytes

    Returns:
        Path to the validated model file

    Raises:
        ModelDownloadError: If download or validation fails
    """
    logger = logger or logging.getLogger(__name__)

    # Validate and prepare target directory
    models_dir = Path(models_dir)
    try:
        models_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ModelDownloadError(
            f"Cannot create models directory {models_dir}: {e}"
        ) from e

    # Check if we can write to the directory
    if not os.access(models_dir, os.W_OK):
        raise ModelDownloadError(f"Models directory {models_dir} is not writable")

    target_path = models_dir / spec.filename

    # Reject symlink placeholders and only trust regular files.
    if target_path.exists():
        if target_path.is_symlink():
            logger.warning(
                "Existing model path %s is a symlink; replacing it with a regular file",
                target_path,
            )
            try:
                target_path.unlink()
            except OSError as e:
                raise ModelDownloadError(
                    f"Failed to remove symlinked model file {target_path}: {e}"
                ) from e
        elif target_path.is_file():
            try:
                size = target_path.stat().st_size
                if size > 0:
                    if validate_gguf and not _validate_gguf_file(target_path, logger):
                        logger.warning(
                            f"Existing file {target_path} failed GGUF validation, re-downloading"
                        )
                    else:
                        logger.info(f"Model already exists: {target_path} ({size:,} bytes)")
                        return target_path
            except OSError as e:
                logger.warning(f"Cannot stat existing file {target_path}: {e}")
        else:
            raise ModelDownloadError(
                f"Model path exists but is not a regular file: {target_path}"
            )

    # Download from Hugging Face using hf_hub_download (more reliable than snapshot_download)
    logger.info(
        f"Downloading model from {spec.repo_id}/{spec.filename} "
        f"(revision: {spec.revision or 'main'})"
    )

    try:
        # Use hf_hub_download instead of snapshot_download
        # This is simpler and handles single files better
        logger.info("Downloading from Hugging Face Hub...")
        downloaded_path = hf_hub_download(
            repo_id=spec.repo_id,
            filename=spec.filename,
            revision=spec.revision,
            resume_download=True,
            token=hf_token,
        )
        logger.info(f"Download complete: {downloaded_path}")

        snapshot_path = Path(downloaded_path)

        if not snapshot_path.is_file():
            raise ModelDownloadError(f"Downloaded file does not exist: {snapshot_path}")

    except RepositoryNotFoundError as e:
        raise ModelDownloadError(
            f"Repository not found: {spec.repo_id}. "
            f"Check that the repo exists and you have access."
        ) from e
    except HfHubHTTPError as e:
        if "404" in str(e):
            raise ModelDownloadError(
                f"File not found: {spec.filename} in {spec.repo_id}. "
                f"Check that the filename is correct and the file exists in the repo."
            ) from e
        raise ModelDownloadError(
            f"HTTP error downloading from {spec.repo_id}: {e}"
        ) from e
    except Exception as e:
        raise ModelDownloadError(
            f"Failed to download model from {spec.repo_id}: {e}"
        ) from e

    # Validate GGUF format
    if validate_gguf and not _validate_gguf_file(snapshot_path, logger):
        raise ModelDownloadError(
            f"Downloaded file {snapshot_path} is not a valid GGUF file"
        )

    # Copy to target location atomically
    try:
        # Use temp file + atomic rename for safety
        temp_path = target_path.with_suffix(".tmp")

        try:
            # Try hardlink first (fastest, zero disk usage)
            if temp_path.exists():
                temp_path.unlink()
            temp_path.hardlink_to(snapshot_path)
            logger.debug(f"Created hardlink to {snapshot_path}")
        except (OSError, NotImplementedError):
            # Hardlink failed, copy instead
            logger.debug("Hardlink failed, copying file...")
            shutil.copy2(snapshot_path, temp_path)
            size = snapshot_path.stat().st_size
            logger.debug(f"Copied {size:,} bytes")

        # Atomic rename
        if target_path.exists():
            target_path.unlink()
        temp_path.rename(target_path)

        logger.info(f"Model ready at {target_path}")
        return target_path

    except OSError as e:
        # Cleanup temp file on failure
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise ModelDownloadError(
            f"Failed to install model to {target_path}: {e}"
        ) from e

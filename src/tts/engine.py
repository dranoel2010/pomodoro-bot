import logging
import shutil
from pathlib import Path
from typing import Any, Optional
from piper.voice import PiperVoice
import numpy as np
from huggingface_hub import hf_hub_download
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError

from .config import TTSConfig


class TTSError(Exception):
    """Raised when text-to-speech processing fails."""

    pass


class PiperTTSEngine:
    def __init__(
        self,
        config: TTSConfig,
        logger: Optional[logging.Logger] = None,
    ):
        self._config = config
        self._logger = logger or logging.getLogger(__name__)
        model_path = self._ensure_model_files()

        try:
            self._voice = PiperVoice.load(str(model_path))
            self._sample_rate_hz = int(self._voice.config.sample_rate)
        except Exception as error:
            raise TTSError(f"Failed to initialize Piper TTS engine: {error}") from error

    def _ensure_model_files(self) -> Path:
        model_dir = Path(self._config.model_path).expanduser()
        model_file = model_dir / self._config.hf_filename
        config_file = model_dir / f"{self._config.hf_filename}.json"

        try:
            model_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise TTSError(
                f"Failed to create TTS model directory {model_dir}: {error}"
            ) from error

        if model_file.is_file() and config_file.is_file():
            return model_file

        missing_assets: list[str] = []
        if not model_file.is_file():
            missing_assets.append(model_file.name)
        if not config_file.is_file():
            missing_assets.append(config_file.name)

        repo_id = self._config.hf_repo_id.strip()
        if not repo_id:
            raise TTSError(
                "Piper model assets are missing: "
                f"{', '.join(missing_assets)}. "
                "Provide the files in tts.model_path or set tts.hf_repo_id for auto-download."
            )

        self._logger.info(
            "Piper model assets not found locally (%s), downloading from %s into %s",
            ", ".join(missing_assets),
            repo_id,
            model_dir,
        )

        self._download_and_install_file(
            repo_id=repo_id,
            filename=self._config.hf_filename,
            target_path=model_file,
        )
        self._download_and_install_file(
            repo_id=repo_id,
            filename=f"{self._config.hf_filename}.json",
            target_path=config_file,
        )

        if not model_file.is_file() or not config_file.is_file():
            raise TTSError(
                "Downloaded Piper assets are incomplete. "
                f"Expected {model_file.name} and {config_file.name} in {model_dir}."
            )

        return model_file

    def _download_and_install_file(
        self,
        *,
        repo_id: str,
        filename: str,
        target_path: Path,
    ) -> None:
        try:
            downloaded_path = Path(
                hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    revision=self._config.hf_revision,
                    resume_download=True,
                )
            )
        except RepositoryNotFoundError as error:
            raise TTSError(
                f"Piper Hugging Face repository not found: {repo_id}"
            ) from error
        except HfHubHTTPError as error:
            if "404" in str(error):
                raise TTSError(
                    f"Piper asset not found in {repo_id}: {filename}"
                ) from error
            raise TTSError(
                f"HTTP error downloading Piper asset {filename} from {repo_id}: {error}"
            ) from error
        except Exception as error:
            raise TTSError(
                f"Failed to download Piper asset {filename} from {repo_id}: {error}"
            ) from error

        if not downloaded_path.is_file():
            raise TTSError(f"Downloaded Piper asset is not a file: {downloaded_path}")

        self._install_file(downloaded_path, target_path)

    @staticmethod
    def _install_file(source_path: Path, target_path: Path) -> None:
        temp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
        try:
            if temp_path.exists():
                temp_path.unlink()

            try:
                temp_path.hardlink_to(source_path)
            except (OSError, NotImplementedError):
                shutil.copy2(source_path, temp_path)

            if target_path.exists():
                target_path.unlink()
            temp_path.rename(target_path)
        except OSError as error:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise TTSError(
                f"Failed to install Piper asset {target_path.name}: {error}"
            ) from error

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        if not text.strip():
            raise TTSError("Text to synthesize cannot be empty")

        try:
            audio_chunks: list[bytes] = []
            for chunk in self._voice.synthesize(text):
                audio_chunks.append(self._extract_chunk_bytes(chunk))

            if not audio_chunks:
                raise TTSError("Piper synthesis produced an empty audio stream")

            pcm_bytes = b"".join(audio_chunks)
            pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
            if pcm_int16.size == 0:
                raise TTSError("Piper synthesis produced an empty audio buffer")

            wav = pcm_int16.astype(np.float32) / 32768.0
            return wav, self._sample_rate_hz
        except TTSError:
            raise
        except Exception as error:
            raise TTSError(f"TTS synthesis failed: {error}") from error

    @staticmethod
    def _extract_chunk_bytes(chunk: Any) -> bytes:
        if hasattr(chunk, "audio_int16_bytes"):
            raw_audio = chunk.audio_int16_bytes
        elif hasattr(chunk, "audio_data"):
            raw_audio = chunk.audio_data
        else:
            raw_audio = chunk

        if isinstance(raw_audio, np.ndarray):
            if raw_audio.dtype != np.int16:
                raw_audio = raw_audio.astype(np.int16, copy=False)
            return raw_audio.tobytes()
        if isinstance(raw_audio, (bytes, bytearray)):
            return bytes(raw_audio)
        if isinstance(raw_audio, memoryview):
            return raw_audio.tobytes()
        if isinstance(raw_audio, (list, tuple)):
            return np.asarray(raw_audio, dtype=np.int16).tobytes()

        try:
            return bytes(raw_audio)
        except Exception as error:
            raise TTSError(
                f"Unsupported Piper chunk audio type: {type(raw_audio).__name__}"
            ) from error


# Backward-compatible alias for imports that still refer to CoquiTTSEngine.
CoquiTTSEngine = PiperTTSEngine

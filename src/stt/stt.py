"""faster-whisper transcription adapters used by runtime utterance handling."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np
from faster_whisper import WhisperModel
from .events import Utterance


@dataclass(frozen=True)
class TranscriptionResult:
    """Structured transcription payload returned by STT backends."""
    text: str
    language: str
    confidence: Optional[float] = None


class STTError(Exception):
    """Raised when speech-to-text processing fails."""

    pass


class FasterWhisperSTT:
    """Speech-to-text using faster-whisper."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = "en",
        beam_size: int = 5,
        vad_filter: bool = True,
        download_root: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize faster-whisper STT.

        Args:
            model_size: Model size ("tiny", "base", "small", "medium", "large-v2", "large-v3")
            device: Device to use ("cpu", "cuda", "auto")
            compute_type: Quantization type ("int8", "int8_float16", "float16", "float32")
                         int8 recommended for Pi 5 (fastest, low memory)
            language: Language code (None for auto-detect)
            beam_size: Beam size for decoding (higher = more accurate but slower)
            vad_filter: Use voice activity detection to filter out non-speech
            logger: Optional logger instance
        """
        self._language = language
        self._beam_size = beam_size
        self._vad_filter = vad_filter
        self._logger = logger or logging.getLogger(__name__)

        self._logger.debug(
            f"Loading faster-whisper model: {model_size} "
            f"(device={device}, compute_type={compute_type})"
        )

        download_root_path = self._resolve_download_root(download_root)
        self._logger.debug("Using faster-whisper download root: %s", download_root_path)

        try:
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                download_root=str(download_root_path),
            )
            self._logger.debug("Model loaded successfully")
        except Exception as e:
            raise STTError(f"Failed to load model: {e}") from e

    @staticmethod
    def _resolve_download_root(download_root: Optional[str]) -> Path:
        root = (
            Path(download_root).expanduser()
            if download_root and download_root.strip()
            else Path("models") / "stt"
        )
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise STTError(
                f"Failed to create STT model download directory {root}: {error}"
            ) from error
        return root

    def transcribe(self, utterance: Utterance) -> TranscriptionResult:
        """Transcribe an utterance to text.

        Args:
            utterance: The audio utterance to transcribe

        Returns:
            TranscriptionResult with the transcribed text

        Raises:
            STTError: If transcription fails
        """
        try:
            # Convert utterance to numpy array format expected by faster-whisper
            # Convert bytes to int16 array
            audio_int16 = np.frombuffer(utterance.audio_bytes, dtype=np.int16)

            # Convert to float32 in range [-1, 1]
            audio_float32 = audio_int16.astype(np.float32) / 32768.0

            self._logger.debug(
                f"Transcribing {utterance.duration_seconds:.2f}s audio "
                f"({len(utterance.audio_bytes)} bytes)"
            )

            # Transcribe
            segments, info = self._model.transcribe(
                audio_float32,
                language=self._language,
                beam_size=self._beam_size,
                vad_filter=self._vad_filter,
                without_timestamps=True,  # We don't need word-level timestamps
            )

            # Collect all segments into single text
            text_parts = []
            avg_confidence = 0.0
            segment_count = 0

            for segment in segments:
                text_parts.append(segment.text.strip())
                if hasattr(segment, "avg_logprob"):
                    # Convert log probability to rough confidence
                    avg_confidence += segment.avg_logprob
                    segment_count += 1

            text = " ".join(text_parts).strip()

            # Calculate average confidence if available
            confidence = None
            if segment_count > 0:
                # Convert avg log prob to approximate confidence (0-1)
                # Note: This is a rough approximation
                avg_logprob = avg_confidence / segment_count
                confidence = max(0.0, min(1.0, np.exp(avg_logprob)))

            # Fix: Format confidence separately
            confidence_str = f"{confidence:.2f}" if confidence is not None else "N/A"
            self._logger.debug(
                f"Transcribed: '{text}' "
                f"(language={info.language}, confidence={confidence_str})"
            )

            if not text:
                self._logger.warning("No speech detected in audio")

            return TranscriptionResult(
                text=text,
                language=info.language,
                confidence=confidence,
            )

        except Exception as e:
            self._logger.error(f"Transcription failed: {e}", exc_info=True)
            raise STTError(f"Transcription failed: {e}") from e


class StreamingFasterWhisperSTT(FasterWhisperSTT):
    """Streaming version that can handle continuous audio."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = "en",
        beam_size: int = 5,
        vad_filter: bool = True,
        min_silence_duration_ms: int = 500,
        download_root: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize streaming faster-whisper STT.

        Args:
            min_silence_duration_ms: Minimum silence duration to split on (ms)
            (other args same as FasterWhisperSTT)
        """
        super().__init__(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            download_root=download_root,
            logger=logger,
        )
        self._min_silence_duration_ms = min_silence_duration_ms

    def transcribe_streaming(self, utterance: Utterance) -> list[TranscriptionResult]:
        """Transcribe with streaming-like segmentation.

        Returns:
            List of transcription results for each detected segment
        """
        try:
            audio_int16 = np.frombuffer(utterance.audio_bytes, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0

            segments, info = self._model.transcribe(
                audio_float32,
                language=self._language,
                beam_size=self._beam_size,
                vad_filter=self._vad_filter,
                vad_parameters={
                    "min_silence_duration_ms": self._min_silence_duration_ms,
                },
                without_timestamps=False,  # Need timestamps for streaming
            )

            results = []
            for segment in segments:
                text = segment.text.strip()
                if text:
                    confidence = None
                    if hasattr(segment, "avg_logprob"):
                        confidence = max(0.0, min(1.0, np.exp(segment.avg_logprob)))

                    results.append(
                        TranscriptionResult(
                            text=text,
                            language=info.language,
                            confidence=confidence,
                        )
                    )

            return results

        except Exception as e:
            self._logger.error(f"Streaming transcription failed: {e}", exc_info=True)
            raise STTError(f"Streaming transcription failed: {e}") from e

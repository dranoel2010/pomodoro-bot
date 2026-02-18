import logging
import math  # ✅ Moved to module scope
import struct
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional

from pvrecorder import PvRecorder

from .events import Utterance
from .vad import VoiceActivityDetector


class CaptureState(Enum):
    """State machine for utterance capture."""

    WAITING_FOR_SPEECH = auto()
    CAPTURING_SPEECH = auto()
    TRAILING_SILENCE = auto()
    COMPLETE = auto()
    TIMEOUT = auto()


@dataclass
class CaptureContext:
    """Context for utterance capture state machine."""

    frames: bytearray = field(default_factory=bytearray)
    frame_count: int = 0
    speech_frame_count: int = 0
    silence_frame_count: int = 0
    state: CaptureState = CaptureState.WAITING_FOR_SPEECH


class UtteranceCapture:
    """Handles capturing utterances after wake word detection."""

    def __init__(
        self,
        vad: VoiceActivityDetector,
        silence_timeout_seconds: float,
        max_utterance_seconds: float,
        no_speech_timeout_seconds: float,
        min_speech_seconds: float,
        logger: Optional[logging.Logger] = None,
    ):
        self._vad = vad
        self._silence_timeout_seconds = silence_timeout_seconds
        self._max_utterance_seconds = max_utterance_seconds
        self._no_speech_timeout_seconds = no_speech_timeout_seconds
        self._min_speech_seconds = min_speech_seconds
        self._logger = logger or logging.getLogger(__name__)

    def capture(
        self,
        recorder: PvRecorder,
        sample_rate: int,
        frame_length: int,
        stop_event: threading.Event,
    ) -> Optional[Utterance]:
        """Capture user utterance after wake word detection.

        Uses a state machine to track speech activity and determine when
        the utterance is complete.
        """
        # Calculate frame limits
        frames_per_second = sample_rate / frame_length
        max_frames = max(1, int(self._max_utterance_seconds * frames_per_second))
        silence_limit_frames = max(
            1, int(self._silence_timeout_seconds * frames_per_second)
        )
        no_speech_limit_frames = max(
            1, int(self._no_speech_timeout_seconds * frames_per_second)
        )
        min_speech_frames = max(1, int(self._min_speech_seconds * frames_per_second))

        # Initialize capture context
        ctx = CaptureContext()
        bytes_per_frame = frame_length * 2  # 16-bit samples = 2 bytes each

        # Pre-allocate buffer for efficiency
        estimated_bytes = max_frames * bytes_per_frame
        ctx.frames = bytearray(estimated_bytes)
        write_offset = 0

        self._logger.debug(
            f"Starting utterance capture (threshold={self._vad.threshold:.2f}, "
            f"min_speech_frames={min_speech_frames}, "
            f"no_speech_limit={no_speech_limit_frames})"
        )

        # Track energy levels for diagnostics
        max_energy_seen = 0.0
        voice_frame_energies = []

        while not stop_event.is_set() and ctx.frame_count < max_frames:
            pcm = recorder.read()

            # Write PCM data directly to buffer
            frame_bytes = struct.pack(f"<{len(pcm)}h", *pcm)
            ctx.frames[write_offset : write_offset + len(frame_bytes)] = frame_bytes
            write_offset += len(frame_bytes)
            ctx.frame_count += 1

            has_voice = self._vad.is_voice_active(pcm)

            # Track energy for diagnostics
            if pcm:
                mean_square = sum(sample * sample for sample in pcm) / len(pcm)
                rms = math.sqrt(mean_square)
                max_energy_seen = max(max_energy_seen, rms)
                if has_voice:
                    voice_frame_energies.append(rms)

            # State machine transitions
            ctx.state = self._transition_state(
                ctx,
                has_voice,
                min_speech_frames,
                silence_limit_frames,
                no_speech_limit_frames,
            )

            if ctx.state in (CaptureState.COMPLETE, CaptureState.TIMEOUT):
                break

        # Diagnostic logging - reduced to DEBUG level
        self._logger.debug(
            f"Capture ended: state={ctx.state.name}, "
            f"speech_frames={ctx.speech_frame_count}/{min_speech_frames}, "
            f"total_frames={ctx.frame_count}, "
            f"max_energy={max_energy_seen:.2f}, "
            f"threshold={self._vad.threshold:.2f}"
        )

        if voice_frame_energies:
            avg_voice_energy = sum(voice_frame_energies) / len(voice_frame_energies)
            self._logger.debug(
                f"Voice activity: {len(voice_frame_energies)} frames detected, "
                f"avg_energy={avg_voice_energy:.2f}"
            )
        else:
            self._logger.warning(
                f"No voice activity detected. Max energy seen: {max_energy_seen:.2f}, "
                f"Threshold: {self._vad.threshold:.2f}"
            )

        # Validate captured utterance
        if ctx.speech_frame_count < min_speech_frames:
            self._logger.debug(
                f"Insufficient speech: {ctx.speech_frame_count} frames < {min_speech_frames} required"
            )

            # Provide actionable feedback at WARNING level (only on failures)
            if max_energy_seen < self._vad.threshold * 0.5:
                self._logger.warning(
                    "Energy levels very low. Try speaking louder or adjusting microphone position."
                )
            elif max_energy_seen < self._vad.threshold:
                self._logger.warning(
                    f"Energy threshold may be too high ({self._vad.threshold:.2f}). "
                    f"Consider lowering energy_threshold config."
                )

            return None

        # Trim trailing silence
        if ctx.state == CaptureState.COMPLETE and ctx.silence_frame_count > 0:
            trim_bytes = ctx.silence_frame_count * bytes_per_frame
            write_offset -= trim_bytes
            self._logger.debug(f"Trimmed {ctx.silence_frame_count} silence frames")

        # Create utterance
        utterance = Utterance(
            audio_bytes=bytes(ctx.frames[:write_offset]),
            sample_rate_hz=sample_rate,
            created_at=datetime.now(timezone.utc),
        )

        # Log at DEBUG level only - service layer will log success at INFO
        self._logger.debug(
            f"Captured {ctx.speech_frame_count} speech frames, "
            f"{utterance.duration_seconds:.2f}s, "
            f"{len(utterance.audio_bytes):,} bytes"
        )

        return utterance

    def _transition_state(
        self,
        ctx: CaptureContext,
        has_voice: bool,
        min_speech_frames: int,
        silence_limit_frames: int,
        no_speech_limit_frames: int,
    ) -> CaptureState:
        """Execute state machine transition based on voice activity."""
        if ctx.state == CaptureState.WAITING_FOR_SPEECH:
            if has_voice:
                ctx.speech_frame_count = 1
                ctx.silence_frame_count = 0
                self._logger.debug("Speech detected, capturing...")
                return CaptureState.CAPTURING_SPEECH
            elif ctx.frame_count >= no_speech_limit_frames:
                self._logger.debug(
                    f"No speech detected after {ctx.frame_count} frames "
                    f"({ctx.frame_count / no_speech_limit_frames:.1f}x timeout)"
                )
                return CaptureState.TIMEOUT
            return CaptureState.WAITING_FOR_SPEECH

        elif ctx.state == CaptureState.CAPTURING_SPEECH:
            if has_voice:
                ctx.speech_frame_count += 1
                ctx.silence_frame_count = 0
                return CaptureState.CAPTURING_SPEECH
            else:
                ctx.silence_frame_count += 1

                # Early timeout: if we've had lots of silence and still haven't
                # reached min speech, give up early instead of waiting max_frames
                if (
                    ctx.silence_frame_count >= silence_limit_frames
                    and ctx.speech_frame_count < min_speech_frames
                ):
                    self._logger.debug(
                        f"Early timeout: {ctx.speech_frame_count} speech frames "
                        f"< {min_speech_frames} required after {ctx.silence_frame_count} silence frames"
                    )
                    return CaptureState.TIMEOUT

                if ctx.speech_frame_count >= min_speech_frames:
                    return CaptureState.TRAILING_SILENCE
                else:
                    # Not enough speech yet, keep waiting
                    return CaptureState.CAPTURING_SPEECH

        elif ctx.state == CaptureState.TRAILING_SILENCE:
            if has_voice:
                # Speech resumed
                ctx.speech_frame_count += 1
                ctx.silence_frame_count = 0
                return CaptureState.CAPTURING_SPEECH
            else:
                ctx.silence_frame_count += 1
                if ctx.silence_frame_count >= silence_limit_frames:
                    self._logger.debug("Utterance complete")
                    return CaptureState.COMPLETE
                return CaptureState.TRAILING_SILENCE

        return ctx.state

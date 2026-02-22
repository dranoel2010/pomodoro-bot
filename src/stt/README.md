# stt module

## Purpose
Wake-word detection, utterance capture, and speech-to-text transcription components.

## Key files
- `config.py`: `WakeWordConfig` and `STTConfig` models.
- `service.py`: `WakeWordService` lifecycle and capture loop.
- `capture.py`: utterance state machine and silence handling.
- `vad.py`: energy-based VAD.
- `stt.py`: faster-whisper transcription adapters.
- `events.py`: event dataclasses and publisher contracts.

## Configuration
From `config.toml`:
- `[wake_word]`: `ppn_file`, `pv_file`, `device_index`, timing and VAD tuning fields.
- `[stt]`: `model_size`, `device`, `compute_type`, `language`, `beam_size`, `vad_filter`.

Secrets from environment:
- `PICO_VOICE_ACCESS_KEY`

## Integration notes
- `WakeWordService` emits events (`WakeWordDetectedEvent`, `UtteranceCapturedEvent`, `WakeWordErrorEvent`).
- Runtime consumes emitted utterances and forwards them to `FasterWhisperSTT`.
- Adaptive thresholding calibrates against ambient noise on startup.
- `FasterWhisperSTT` stores downloaded whisper checkpoints in `models/stt` by default.

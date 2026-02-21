# tts module

Text-to-speech synthesis and playback module.

## Purpose

- Load Piper TTS model assets.
- Synthesize text to mono PCM audio.
- Play synthesized audio through `sounddevice`.

## Main components

- `config.py`: `TTSConfig` from environment.
- `engine.py`: `PiperTTSEngine` and `TTSError`.
- `output.py`: `SoundDeviceAudioOutput`.
- `service.py`: `SpeechService` orchestration.

## Environment variables

Configured via `[tts]` in `config.toml`:
- `model_path`: local directory for Piper model files.
- `hf_filename`: ONNX model filename (for example `de_DE-thorsten-high.onnx`).
- `hf_repo_id`: optional Hugging Face repo used for auto-download when files are missing.
- `hf_revision`: optional model revision (defaults to `main`).
- `output_device`: optional output device index for `sounddevice`.

## Integration

`src/main.py` creates `SpeechService` when TTS is enabled and speaks LLM responses.

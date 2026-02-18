# tts module

Text-to-speech synthesis and playback module.

## Purpose

- Load Coqui TTS model assets.
- Synthesize text to mono PCM audio.
- Play synthesized audio through `sounddevice`.

## Main components

- `config.py`: `TTSConfig` from environment.
- `engine.py`: `CoquiTTSEngine` and `TTSError`.
- `output.py`: `SoundDeviceAudioOutput`.
- `service.py`: `SpeechService` orchestration.

## Environment variables

Required when `TTS_ENABLED=true`:
- `TTS_MODEL_PATH`: path to model weights file.
- `TTS_CONFIG_PATH`: path to model config file.

Optional:
- `TTS_ENABLED`: enable TTS in `src/main.py` (`true`/`false`).
- `TTS_OUTPUT_DEVICE`: numeric output device index for `sounddevice`.
- `TTS_GPU`: use GPU (`true`/`false`).
- `TTS_HF_REPO_ID`: Hugging Face repo for fallback download if local files are missing.
- `TTS_HF_LOCAL_DIR`: directory where fallback download is stored.

## Integration

`src/main.py` creates `SpeechService` when TTS is enabled and speaks LLM responses.

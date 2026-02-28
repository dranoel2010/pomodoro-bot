# tts module

## Purpose
Text-to-speech synthesis and playback based on Piper and sounddevice.

## Key files
- `config.py`: `TTSConfig` validation.
- `factory.py`: `create_tts_config(...)` for validated TTS config only.
- `engine.py`: `PiperTTSEngine` model management and synthesis.
- `output.py`: `SoundDeviceAudioOutput` playback adapter.
- `service.py`: `SpeechService` facade.

## Configuration
From `config.toml` (`[tts]`):
- `enabled`
- `model_path`
- `hf_filename`
- `hf_repo_id`
- `hf_revision`
- `output_device`
- `cpu_cores`

## Integration notes
- Missing local model assets trigger optional Hugging Face download when `hf_repo_id` is set.
- Runtime uses `SpeechService.speak()` for assistant replies and completion announcements.
- Worker process creation and enabled/disabled gating live in `runtime.workers.tts.create_tts_worker(...)`.
- TTS worker requests are explicit typed payloads and runtime state stays process-local.

# stt module

Reusable wake-word and utterance-capture module with queue/event-based integration points.

## Responsibilities

- Wake-word detection via Porcupine.
- Utterance capture after wake-word detection.
- Voice activity detection (RMS energy + adaptive threshold from ambient noise floor).
- Optional speech-to-text via faster-whisper.
- Event publication to decouple detection/capture from application logic.

## Module structure

- `__init__.py`: public API exports.
- `config.py`: `WakeWordConfig`, `STTConfig`, `ConfigurationError`.
- `events.py`: event contracts and queue publisher.
- `vad.py`: `VoiceActivityDetector`.
- `capture.py`: utterance state machine and audio buffer handling.
- `service.py`: `WakeWordService` lifecycle + orchestration.
- `stt.py`: `FasterWhisperSTT`, streaming variant, and transcription result/error types.

## Event model

- `WakeWordDetectedEvent`: emitted when wake word is matched.
- `UtteranceCapturedEvent`: emitted when a valid utterance is captured.
- `WakeWordErrorEvent`: emitted on service/runtime failure.

`QueueEventPublisher` pushes these events to a `queue.Queue`, but any publisher implementing the `EventPublisher` protocol can be injected.

## Main classes

- `WakeWordService`
  - `start()` / `stop()`
  - `is_running`, `is_ready`, `wait_until_ready()`
- `UtteranceCapture`
  - captures audio until completion/timeout based on VAD and silence rules
- `VoiceActivityDetector`
  - computes RMS frame energy and compares against dynamic threshold
- `FasterWhisperSTT`
  - transcribes captured `Utterance` to text

## Minimal integration example

```python
from queue import Queue

from stt import (
    QueueEventPublisher,
    WakeWordConfig,
    WakeWordService,
    WakeWordDetectedEvent,
    UtteranceCapturedEvent,
    WakeWordErrorEvent,
)
from app_config import load_app_config, load_secret_config

app_config = load_app_config()
secrets = load_secret_config()
event_queue = Queue()
publisher = QueueEventPublisher(event_queue)
service = WakeWordService(
    config=WakeWordConfig.from_settings(
        pico_voice_access_key=secrets.pico_voice_access_key,
        settings=app_config.wake_word,
    ),
    publisher=publisher,
)

service.start()
try:
    while True:
        event = event_queue.get()
        if isinstance(event, WakeWordDetectedEvent):
            print("wake word detected")
        elif isinstance(event, UtteranceCapturedEvent):
            print("utterance bytes:", len(event.utterance.audio_bytes))
        elif isinstance(event, WakeWordErrorEvent):
            print("error:", event.message)
            break
finally:
    service.stop()
```

## Configuration

### Wake word

- Required:
  - `PICO_VOICE_ACCESS_KEY`
  - `PORCUPINE_PPN_FILE`
  - `PORCUPINE_PV_FILE`
- `WakeWordConfig` key fields:
  - `pico_voice_access_key`
  - `porcupine_wake_word_file`
  - `porcupine_model_params_file`
  - `device_index`
  - `silence_timeout_seconds`
  - `max_utterance_seconds`
  - `no_speech_timeout_seconds`
  - `min_speech_seconds`
  - `energy_threshold`
  - `noise_floor_calibration_seconds`
  - `adaptive_threshold_multiplier`

### STT (optional/customizable)

- `WHISPER_MODEL_SIZE`
- `WHISPER_DEVICE`
- `WHISPER_COMPUTE_TYPE`
- `WHISPER_LANGUAGE`
- `WHISPER_BEAM_SIZE`
- `WHISPER_VAD_FILTER`

## Extensibility points

- Replace queue transport with your own `EventPublisher`.
- Replace or wrap STT implementation without changing wake-word capture.
- Tune VAD/capture sensitivity through `WakeWordConfig`.

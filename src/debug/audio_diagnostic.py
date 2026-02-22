"""Diagnostic tool to help tune VAD settings."""

import logging
import math
import sys
import time

import pvporcupine
from pvrecorder import PvRecorder

from app_config import AppConfigurationError, load_app_config, load_secret_config, resolve_config_path
from stt import WakeWordConfig, ConfigurationError


def setup_logging():
    """Configure console logging for the diagnostic tool."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )


def main():
    """Run interactive microphone diagnostics for wake-word VAD tuning."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        app_config = load_app_config(str(resolve_config_path()))
        secret_config = load_secret_config()
        config = WakeWordConfig.from_settings(
            pico_voice_access_key=secret_config.pico_voice_access_key,
            settings=app_config.wake_word,
        )
    except (AppConfigurationError, ConfigurationError) as e:
        print(f"Error: {e}")
        return 1

    print("=== Wake Word VAD Diagnostic Tool ===\n")
    print("This tool will help you tune your voice activity detection settings.")
    print("Speak into your microphone for 5 seconds...\n")

    porcupine = None
    recorder = None

    try:
        porcupine = pvporcupine.create(
            access_key=config.pico_voice_access_key,
            keyword_paths=[config.porcupine_wake_word_file],
            model_path=config.porcupine_model_params_file,
        )

        recorder = PvRecorder(
            frame_length=porcupine.frame_length, device_index=config.device_index
        )
        recorder.start()

        print("Recording background noise for 2 seconds (stay quiet)...")
        time.sleep(0.5)

        noise_samples = []
        for _ in range(int(2 * porcupine.sample_rate / porcupine.frame_length)):
            pcm = recorder.read()
            if pcm:
                mean_square = sum(s * s for s in pcm) / len(pcm)
                rms = math.sqrt(mean_square)
                noise_samples.append(rms)

        noise_floor = sum(noise_samples) / len(noise_samples) if noise_samples else 0
        print(f"✓ Noise floor: {noise_floor:.2f}")

        print("\nNow speak normally into the microphone for 5 seconds...")
        time.sleep(0.5)

        speech_samples = []
        for _ in range(int(5 * porcupine.sample_rate / porcupine.frame_length)):
            pcm = recorder.read()
            if pcm:
                mean_square = sum(s * s for s in pcm) / len(pcm)
                rms = math.sqrt(mean_square)
                speech_samples.append(rms)

        if speech_samples:
            max_speech = max(speech_samples)
            avg_speech = sum(speech_samples) / len(speech_samples)

            print(f"\n✓ Speech levels:")
            print(f"  - Average: {avg_speech:.2f}")
            print(f"  - Peak: {max_speech:.2f}")
            print(f"\n✓ Current config:")
            print(f"  - energy_threshold: {config.energy_threshold:.2f}")
            print(
                f"  - adaptive_threshold_multiplier: {config.adaptive_threshold_multiplier:.2f}"
            )
            print(
                f"  - Adaptive threshold would be: {noise_floor * config.adaptive_threshold_multiplier:.2f}"
            )

            recommended_threshold = noise_floor * 2.5

            print(f"\n📊 Analysis:")
            if max_speech < config.energy_threshold:
                print(
                    f"  ⚠️  Your speech ({max_speech:.2f}) is below threshold ({config.energy_threshold:.2f})"
                )
                print(f"  💡 Recommended energy_threshold: {recommended_threshold:.2f}")
            elif avg_speech < config.energy_threshold * 0.7:
                print(f"  ⚠️  Your average speech is quite low")
                print(
                    f"  💡 Consider lowering energy_threshold to: {recommended_threshold:.2f}"
                )
            else:
                print(f"  ✓ Threshold seems reasonable")

            adaptive_threshold = noise_floor * config.adaptive_threshold_multiplier
            actual_threshold = max(config.energy_threshold, adaptive_threshold)

            print(f"\n  Actual threshold in use: {actual_threshold:.2f}")
            if max_speech < actual_threshold:
                print(f"  ⚠️  Speech below actual threshold!")
                print(f"  💡 Try: energy_threshold={recommended_threshold:.2f}")
                print(f"  💡 Or: adaptive_threshold_multiplier=1.5")

    finally:
        if recorder:
            recorder.stop()
            recorder.delete()
        if porcupine:
            porcupine.delete()

    return 0


if __name__ == "__main__":
    sys.exit(main())

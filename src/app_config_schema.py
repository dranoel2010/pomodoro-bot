"""Dataclass schema objects used by runtime configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

DEFAULT_CONFIG_FILE = "config.toml"


class AppConfigurationError(Exception):
    """Raised when application configuration fails."""


@dataclass(frozen=True)
class WakeWordSettings:
    """Wake-word and capture tuning values loaded from `[wake_word]`."""
    ppn_file: str
    pv_file: str
    device_index: int = 0
    silence_timeout_seconds: float = 1.5
    max_utterance_seconds: float = 10.0
    no_speech_timeout_seconds: float = 3.0
    min_speech_seconds: float = 0.15
    energy_threshold: float = 100.0
    noise_floor_calibration_seconds: float = 1.0
    adaptive_threshold_multiplier: float = 1.5
    validate_paths: bool = True


@dataclass(frozen=True)
class STTSettings:
    """Speech-to-text model and decoding settings from `[stt]`."""
    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: Optional[str] = "en"
    beam_size: int = 5
    vad_filter: bool = True


@dataclass(frozen=True)
class TTSSettings:
    """Text-to-speech settings from `[tts]`."""
    enabled: bool = False
    model_path: str = ""
    hf_filename: str = ""
    hf_repo_id: str = ""
    hf_revision: str = "main"
    gpu: bool = False
    output_device: Optional[int] = None


@dataclass(frozen=True)
class LLMSettings:
    """Local LLM inference and prompt settings from `[llm]`."""
    enabled: bool = False
    model_path: str = ""
    hf_filename: str = ""
    hf_repo_id: str = ""
    hf_revision: str = ""
    system_prompt: str = ""
    n_threads: int = 4
    n_ctx: int = 2048
    n_batch: int = 256
    temperature: float = 0.2
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    verbose: bool = False


@dataclass(frozen=True)
class UIServerSettings:
    """Built-in UI server settings from `[ui_server]`."""
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    ui: str = "jarvis"
    index_file: str = ""


@dataclass(frozen=True)
class OracleSettings:
    """Optional oracle integration settings from `[oracle]`."""
    enabled: bool = True
    ens160_enabled: bool = False
    temt6000_enabled: bool = False
    google_calendar_enabled: bool = False
    google_calendar_max_results: int = 5
    sensor_cache_ttl_seconds: float = 15.0
    calendar_cache_ttl_seconds: float = 60.0
    ens160_temperature_compensation_c: float = 25.0
    ens160_humidity_compensation_pct: float = 50.0
    temt6000_channel: int = 0
    temt6000_gain: int = 1
    temt6000_adc_address: int = 0x48
    temt6000_busnum: int = 1


@dataclass(frozen=True)
class AppConfig:
    """Complete typed runtime configuration loaded from `config.toml`."""
    wake_word: WakeWordSettings
    stt: STTSettings
    tts: TTSSettings
    llm: LLMSettings
    ui_server: UIServerSettings
    oracle: OracleSettings
    source_file: str


@dataclass(frozen=True)
class SecretConfig:
    """Environment-provided secrets kept out of `config.toml`."""
    pico_voice_access_key: str
    hf_token: Optional[str]
    oracle_google_calendar_id: Optional[str]
    oracle_google_service_account_file: Optional[str]

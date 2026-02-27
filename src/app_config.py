"""Pipecat-only configuration loader and schema."""
from __future__ import annotations
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from shared.env_keys import (
    ENV_APP_CONFIG_FILE,
    ENV_HF_TOKEN,
    ENV_ORACLE_GOOGLE_CALENDAR_ID,
    ENV_ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE,
    ENV_PICO_VOICE_ACCESS_KEY,
)
DEFAULT_CONFIG_FILE = "config.toml"
_ALLOWED_UI_VARIANTS = {"jarvis", "miro"}
_ALLOWED_LLM_AFFINITY_MODES = {"pinned", "shared"}

class AppConfigurationError(Exception):
    """Raised when application configuration fails."""
@dataclass(frozen=True)

class PipecatRuntimeSettings:
    language: str = "de"
    allow_interruptions: bool = False
    metrics_enabled: bool = True
@dataclass(frozen=True)

class PorcupineWakeSettings:
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

class WakeSettings:
    porcupine: PorcupineWakeSettings
@dataclass(frozen=True)

class FasterWhisperSTTSettings:
    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str | None = "de"
    beam_size: int = 5
    vad_filter: bool = True
    cpu_threads: int = 0
    cpu_cores: tuple[int, ...] = ()
@dataclass(frozen=True)

class STTSettings:
    faster_whisper: FasterWhisperSTTSettings
@dataclass(frozen=True)

class LocalLlamaLLMSettings:
    enabled: bool = False
    model_path: str = ""
    hf_filename: str = ""
    hf_repo_id: str = ""
    hf_revision: str = ""
    system_prompt: str = ""
    max_tokens: int | None = None
    n_threads: int = 4
    n_threads_batch: int | None = None
    n_ctx: int = 2048
    n_batch: int = 256
    n_ubatch: int | None = None
    temperature: float = 0.2
    top_p: float = 0.9
    top_k: int = 40
    min_p: float = 0.05
    repeat_penalty: float = 1.1
    use_mmap: bool = True
    use_mlock: bool = False
    verbose: bool = False
    fast_path_enabled: bool = True
    cpu_affinity_mode: str = "pinned"
    shared_cpu_reserve_cores: int = 1
    cpu_cores: tuple[int, ...] = ()
@dataclass(frozen=True)

class LLMSettings:
    local_llama: LocalLlamaLLMSettings
@dataclass(frozen=True)

class PiperTTSSettings:
    enabled: bool = False
    model_path: str = ""
    hf_filename: str = ""
    hf_repo_id: str = ""
    hf_revision: str = "main"
    output_device: int | None = None
    cpu_cores: tuple[int, ...] = ()
@dataclass(frozen=True)

class TTSSettings:
    piper: PiperTTSSettings
@dataclass(frozen=True)

class UISettings:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    ui: str = "jarvis"
    index_file: str = ""
@dataclass(frozen=True)

class CalendarToolSettings:
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

class ToolSettings:
    calendar: CalendarToolSettings
@dataclass(frozen=True)

class PipecatSettings:
    runtime: PipecatRuntimeSettings
    wake: WakeSettings
    stt: STTSettings
    llm: LLMSettings
    tts: TTSSettings
    ui: UISettings
    tools: ToolSettings
@dataclass(frozen=True)

class AppConfig:
    pipecat: PipecatSettings
    source_file: str
@dataclass(frozen=True)

class SecretConfig:
    pico_voice_access_key: str
    hf_token: str | None
    oracle_google_calendar_id: str | None
    oracle_google_service_account_file: str | None
Converter = Callable[[Any, str], Any]
FieldSpec = tuple[str, Converter, Any]

def resolve_config_path(config_path: str | None = None) -> Path:
    """Resolve config file path from arg, env, or default location."""
    env_path = os.getenv(ENV_APP_CONFIG_FILE)
    raw = config_path or env_path or DEFAULT_CONFIG_FILE
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    cwd_path = (Path.cwd() / path).resolve()
    if cwd_path.exists():
        return cwd_path
    if config_path is None and env_path is None and getattr(sys, "frozen", False):
        return (Path(sys.executable).resolve().parent / DEFAULT_CONFIG_FILE).resolve()
    return cwd_path

def load_app_config(config_path: str | None = None) -> AppConfig:
    """Load Pipecat-only TOML config."""
    path = resolve_config_path(config_path)
    if not path.exists():
        raise AppConfigurationError(f"Config file not found: {path}")
    if not path.is_file():
        raise AppConfigurationError(f"Config path is not a file: {path}")
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except Exception as error:
        raise AppConfigurationError(f"Failed to parse config TOML: {error}") from error
    if not isinstance(raw, Mapping):
        raise AppConfigurationError("Root config TOML object must be a table")
    pipecat = _section(raw, "pipecat")
    runtime = _parse_runtime(_section(pipecat, "runtime"))
    wake = _parse_wake(_section(pipecat, "wake"), base_dir=path.parent)
    stt = _parse_stt(_section(pipecat, "stt"))
    llm = _parse_llm(_section(pipecat, "llm"), base_dir=path.parent)
    tts = _parse_tts(_section(pipecat, "tts"), base_dir=path.parent)
    ui = _parse_ui(_section(pipecat, "ui"), base_dir=path.parent)
    tools = _parse_tools(_section(pipecat, "tools"))
    return AppConfig(
        pipecat=PipecatSettings(
            runtime=runtime,
            wake=wake,
            stt=stt,
            llm=llm,
            tts=tts,
            ui=ui,
            tools=tools,
        ),
        source_file=str(path),
    )

def load_secret_config(*, environ: Mapping[str, str] | None = None) -> SecretConfig:
    """Load required secrets from environment variables."""
    env = environ if environ is not None else os.environ
    pico = env.get(ENV_PICO_VOICE_ACCESS_KEY, "").strip()
    if not pico:
        raise AppConfigurationError(
            f"{ENV_PICO_VOICE_ACCESS_KEY} must be set as an environment secret."
        )
    return SecretConfig(
        pico_voice_access_key=pico,
        hf_token=env.get(ENV_HF_TOKEN, "").strip() or None,
        oracle_google_calendar_id=env.get(ENV_ORACLE_GOOGLE_CALENDAR_ID, "").strip() or None,
        oracle_google_service_account_file=env.get(
            ENV_ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE,
            "",
        ).strip() or None,
    )

def _parse_runtime(section: Mapping[str, Any]) -> PipecatRuntimeSettings:
    values = _parse_fields(
        section,
        "pipecat.runtime",
        (
            ("language", _to_str, PipecatRuntimeSettings.language),
            ("allow_interruptions", _to_bool, PipecatRuntimeSettings.allow_interruptions),
            ("metrics_enabled", _to_bool, PipecatRuntimeSettings.metrics_enabled),
        ),
    )
    return PipecatRuntimeSettings(**values)

def _parse_wake(section: Mapping[str, Any], *, base_dir: Path) -> WakeSettings:
    porcupine = _section(section, "porcupine")
    values = _parse_fields(
        porcupine,
        "pipecat.wake.porcupine",
        (
            ("ppn_file", _to_required_str, None),
            ("pv_file", _to_required_str, None),
            ("device_index", _to_int, PorcupineWakeSettings.device_index),
            (
                "silence_timeout_seconds",
                _to_float,
                PorcupineWakeSettings.silence_timeout_seconds,
            ),
            (
                "max_utterance_seconds",
                _to_float,
                PorcupineWakeSettings.max_utterance_seconds,
            ),
            (
                "no_speech_timeout_seconds",
                _to_float,
                PorcupineWakeSettings.no_speech_timeout_seconds,
            ),
            ("min_speech_seconds", _to_float, PorcupineWakeSettings.min_speech_seconds),
            ("energy_threshold", _to_float, PorcupineWakeSettings.energy_threshold),
            (
                "noise_floor_calibration_seconds",
                _to_float,
                PorcupineWakeSettings.noise_floor_calibration_seconds,
            ),
            (
                "adaptive_threshold_multiplier",
                _to_float,
                PorcupineWakeSettings.adaptive_threshold_multiplier,
            ),
            ("validate_paths", _to_bool, PorcupineWakeSettings.validate_paths),
        ),
    )
    values["ppn_file"] = _resolve_path(base_dir, values["ppn_file"])
    values["pv_file"] = _resolve_path(base_dir, values["pv_file"])
    return WakeSettings(porcupine=PorcupineWakeSettings(**values))

def _parse_stt(section: Mapping[str, Any]) -> STTSettings:
    values = _parse_fields(
        _section(section, "faster_whisper"),
        "pipecat.stt.faster_whisper",
        (
            ("model_size", _to_str, FasterWhisperSTTSettings.model_size),
            ("device", _to_str, FasterWhisperSTTSettings.device),
            ("compute_type", _to_str, FasterWhisperSTTSettings.compute_type),
            ("language", _to_optional_str, FasterWhisperSTTSettings.language),
            ("beam_size", _to_int, FasterWhisperSTTSettings.beam_size),
            ("vad_filter", _to_bool, FasterWhisperSTTSettings.vad_filter),
            ("cpu_threads", _to_int, FasterWhisperSTTSettings.cpu_threads),
            ("cpu_cores", _to_int_tuple, FasterWhisperSTTSettings.cpu_cores),
        ),
    )
    return STTSettings(faster_whisper=FasterWhisperSTTSettings(**values))

def _parse_llm(section: Mapping[str, Any], *, base_dir: Path) -> LLMSettings:
    values = _parse_fields(
        _section(section, "local_llama"),
        "pipecat.llm.local_llama",
        (
            ("enabled", _to_bool, LocalLlamaLLMSettings.enabled),
            ("model_path", _to_str, LocalLlamaLLMSettings.model_path),
            ("hf_filename", _to_str, LocalLlamaLLMSettings.hf_filename),
            ("hf_repo_id", _to_str, LocalLlamaLLMSettings.hf_repo_id),
            ("hf_revision", _to_str, LocalLlamaLLMSettings.hf_revision),
            ("system_prompt", _to_str, LocalLlamaLLMSettings.system_prompt),
            ("max_tokens", _to_optional_int, LocalLlamaLLMSettings.max_tokens),
            ("n_threads", _to_int, LocalLlamaLLMSettings.n_threads),
            (
                "n_threads_batch",
                _to_optional_int,
                LocalLlamaLLMSettings.n_threads_batch,
            ),
            ("n_ctx", _to_int, LocalLlamaLLMSettings.n_ctx),
            ("n_batch", _to_int, LocalLlamaLLMSettings.n_batch),
            ("n_ubatch", _to_optional_int, LocalLlamaLLMSettings.n_ubatch),
            ("temperature", _to_float, LocalLlamaLLMSettings.temperature),
            ("top_p", _to_float, LocalLlamaLLMSettings.top_p),
            ("top_k", _to_int, LocalLlamaLLMSettings.top_k),
            ("min_p", _to_float, LocalLlamaLLMSettings.min_p),
            ("repeat_penalty", _to_float, LocalLlamaLLMSettings.repeat_penalty),
            ("use_mmap", _to_bool, LocalLlamaLLMSettings.use_mmap),
            ("use_mlock", _to_bool, LocalLlamaLLMSettings.use_mlock),
            ("verbose", _to_bool, LocalLlamaLLMSettings.verbose),
            ("fast_path_enabled", _to_bool, LocalLlamaLLMSettings.fast_path_enabled),
            ("cpu_affinity_mode", _to_str, LocalLlamaLLMSettings.cpu_affinity_mode),
            (
                "shared_cpu_reserve_cores",
                _to_int,
                LocalLlamaLLMSettings.shared_cpu_reserve_cores,
            ),
            ("cpu_cores", _to_int_tuple, LocalLlamaLLMSettings.cpu_cores),
        ),
    )
    affinity_mode = values["cpu_affinity_mode"]
    if affinity_mode not in _ALLOWED_LLM_AFFINITY_MODES:
        allowed = ", ".join(sorted(_ALLOWED_LLM_AFFINITY_MODES))
        raise AppConfigurationError(
            f"pipecat.llm.local_llama.cpu_affinity_mode must be one of: {allowed}"
        )
    if values["model_path"]:
        values["model_path"] = _resolve_path(base_dir, values["model_path"])
    if values["system_prompt"]:
        values["system_prompt"] = _resolve_path(base_dir, values["system_prompt"])
    return LLMSettings(local_llama=LocalLlamaLLMSettings(**values))

def _parse_tts(section: Mapping[str, Any], *, base_dir: Path) -> TTSSettings:
    values = _parse_fields(
        _section(section, "piper"),
        "pipecat.tts.piper",
        (
            ("enabled", _to_bool, PiperTTSSettings.enabled),
            ("model_path", _to_str, PiperTTSSettings.model_path),
            ("hf_filename", _to_str, PiperTTSSettings.hf_filename),
            ("hf_repo_id", _to_str, PiperTTSSettings.hf_repo_id),
            ("hf_revision", _to_str, PiperTTSSettings.hf_revision),
            ("output_device", _to_optional_int, PiperTTSSettings.output_device),
            ("cpu_cores", _to_int_tuple, PiperTTSSettings.cpu_cores),
        ),
    )
    if values["model_path"]:
        values["model_path"] = _resolve_path(base_dir, values["model_path"])
    if not values["hf_revision"]:
        values["hf_revision"] = PiperTTSSettings.hf_revision
    return TTSSettings(piper=PiperTTSSettings(**values))

def _parse_ui(section: Mapping[str, Any], *, base_dir: Path) -> UISettings:
    values = _parse_fields(
        section,
        "pipecat.ui",
        (
            ("enabled", _to_bool, UISettings.enabled),
            ("host", _to_str, UISettings.host),
            ("port", _to_int, UISettings.port),
            ("ui", _to_str, UISettings.ui),
            ("index_file", _to_str, UISettings.index_file),
        ),
    )
    if values["ui"] not in _ALLOWED_UI_VARIANTS:
        allowed = ", ".join(sorted(_ALLOWED_UI_VARIANTS))
        raise AppConfigurationError(f"pipecat.ui.ui must be one of: {allowed}")
    if values["index_file"]:
        values["index_file"] = _resolve_path(base_dir, values["index_file"])
    return UISettings(**values)

def _parse_tools(section: Mapping[str, Any]) -> ToolSettings:
    values = _parse_fields(
        _section(section, "calendar"),
        "pipecat.tools.calendar",
        (
            ("enabled", _to_bool, CalendarToolSettings.enabled),
            ("ens160_enabled", _to_bool, CalendarToolSettings.ens160_enabled),
            ("temt6000_enabled", _to_bool, CalendarToolSettings.temt6000_enabled),
            (
                "google_calendar_enabled",
                _to_bool,
                CalendarToolSettings.google_calendar_enabled,
            ),
            (
                "google_calendar_max_results",
                _to_int,
                CalendarToolSettings.google_calendar_max_results,
            ),
            (
                "sensor_cache_ttl_seconds",
                _to_float,
                CalendarToolSettings.sensor_cache_ttl_seconds,
            ),
            (
                "calendar_cache_ttl_seconds",
                _to_float,
                CalendarToolSettings.calendar_cache_ttl_seconds,
            ),
            (
                "ens160_temperature_compensation_c",
                _to_float,
                CalendarToolSettings.ens160_temperature_compensation_c,
            ),
            (
                "ens160_humidity_compensation_pct",
                _to_float,
                CalendarToolSettings.ens160_humidity_compensation_pct,
            ),
            ("temt6000_channel", _to_int, CalendarToolSettings.temt6000_channel),
            ("temt6000_gain", _to_int, CalendarToolSettings.temt6000_gain),
            (
                "temt6000_adc_address",
                _to_hex_or_int,
                CalendarToolSettings.temt6000_adc_address,
            ),
            ("temt6000_busnum", _to_int, CalendarToolSettings.temt6000_busnum),
        ),
    )
    return ToolSettings(calendar=CalendarToolSettings(**values))

def _parse_fields(
    section: Mapping[str, Any],
    scope: str,
    specs: tuple[FieldSpec, ...],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, converter, default in specs:
        field = f"{scope}.{key}"
        raw = section.get(key, default)
        values[key] = converter(raw, field)
    return values

def _section(raw: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    section = raw.get(key)
    if isinstance(section, Mapping):
        return section
    raise AppConfigurationError(f"Missing or invalid section: {key}")

def _resolve_path(base_dir: Path, raw_path: str) -> str:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())

def _to_str(value: Any, field: str) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    raise AppConfigurationError(f"{field} must be a string")

def _to_required_str(value: Any, field: str) -> str:
    parsed = _to_str(value, field)
    if parsed:
        return parsed
    raise AppConfigurationError(f"Missing required value: {field}")

def _to_optional_str(value: Any, field: str) -> str | None:
    parsed = _to_str(value, field)
    return parsed or None

def _to_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise AppConfigurationError(f"{field} must be a boolean")

def _to_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AppConfigurationError(f"{field} must be an integer")
    return value

def _to_optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _to_int(value, field)

def _to_float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise AppConfigurationError(f"{field} must be numeric")
    if isinstance(value, (int, float)):
        return float(value)
    raise AppConfigurationError(f"{field} must be numeric")

def _to_hex_or_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise AppConfigurationError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip(), 0)
        except ValueError as error:
            raise AppConfigurationError(
                f"{field} must be an integer or hex string"
            ) from error
    raise AppConfigurationError(f"{field} must be an integer or hex string")

def _to_int_tuple(value: Any, field: str) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        raise AppConfigurationError(f"{field} must be an array of integers")
    result: list[int] = []
    seen: set[int] = set()
    for index, item in enumerate(value):
        parsed = _to_int(item, f"{field}[{index}]")
        if parsed in seen:
            raise AppConfigurationError(f"{field} must not contain duplicates")
        seen.add(parsed)
        result.append(parsed)
    return tuple(result)
__all__ = [
    "AppConfig",
    "AppConfigurationError",
    "DEFAULT_CONFIG_FILE",
    "LocalLlamaLLMSettings",
    "PiperTTSSettings",
    "FasterWhisperSTTSettings",
    "PorcupineWakeSettings",
    "SecretConfig",
    "UISettings",
    "CalendarToolSettings",
    "load_app_config",
    "load_secret_config",
    "resolve_config_path",
]

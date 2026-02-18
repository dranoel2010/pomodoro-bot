from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    import tomli as tomllib  # type: ignore


DEFAULT_CONFIG_FILE = "config.toml"


class AppConfigurationError(Exception):
    """Raised when application configuration fails."""


@dataclass(frozen=True)
class WakeWordSettings:
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
    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: Optional[str] = "en"
    beam_size: int = 5
    vad_filter: bool = True


@dataclass(frozen=True)
class TTSSettings:
    enabled: bool = False
    model_path: str = ""
    config_path: str = ""
    gpu: bool = False
    output_device: Optional[int] = None


@dataclass(frozen=True)
class LLMSettings:
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
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    ws_path: str = "/ws"
    index_file: str = ""


@dataclass(frozen=True)
class OracleSettings:
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
    wake_word: WakeWordSettings
    stt: STTSettings
    tts: TTSSettings
    llm: LLMSettings
    ui_server: UIServerSettings
    oracle: OracleSettings
    source_file: str


@dataclass(frozen=True)
class SecretConfig:
    pico_voice_access_key: str
    hf_token: Optional[str]
    oracle_google_calendar_id: Optional[str]
    oracle_google_service_account_file: Optional[str]


def resolve_config_path(config_path: str | None = None) -> Path:
    env_path = os.getenv("APP_CONFIG_FILE")
    raw = config_path or env_path or DEFAULT_CONFIG_FILE
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if path.exists():
        return path

    # Packaged fallback: use bundled config.toml when no explicit path is provided.
    if config_path is None and env_path is None:
        bundle_root = Path(getattr(sys, "_MEIPASS", ""))
        if str(bundle_root):
            bundled_path = bundle_root / DEFAULT_CONFIG_FILE
            if bundled_path.exists():
                return bundled_path

    return path


def load_app_config(config_path: str | None = None) -> AppConfig:
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
        raise AppConfigurationError("Root config TOML object must be a table.")

    base_dir = path.parent

    wake_raw = _section(raw, "wake_word")
    ppn_file = _required_str(wake_raw, "ppn_file", "wake_word")
    pv_file = _required_str(wake_raw, "pv_file", "wake_word")
    wake_word = WakeWordSettings(
        ppn_file=_resolve_path(base_dir, ppn_file),
        pv_file=_resolve_path(base_dir, pv_file),
        device_index=_as_int(wake_raw.get("device_index", 0), "wake_word.device_index"),
        silence_timeout_seconds=_as_float(
            wake_raw.get("silence_timeout_seconds", 1.5),
            "wake_word.silence_timeout_seconds",
        ),
        max_utterance_seconds=_as_float(
            wake_raw.get("max_utterance_seconds", 10.0),
            "wake_word.max_utterance_seconds",
        ),
        no_speech_timeout_seconds=_as_float(
            wake_raw.get("no_speech_timeout_seconds", 3.0),
            "wake_word.no_speech_timeout_seconds",
        ),
        min_speech_seconds=_as_float(
            wake_raw.get("min_speech_seconds", 0.15),
            "wake_word.min_speech_seconds",
        ),
        energy_threshold=_as_float(
            wake_raw.get("energy_threshold", 100.0),
            "wake_word.energy_threshold",
        ),
        noise_floor_calibration_seconds=_as_float(
            wake_raw.get("noise_floor_calibration_seconds", 1.0),
            "wake_word.noise_floor_calibration_seconds",
        ),
        adaptive_threshold_multiplier=_as_float(
            wake_raw.get("adaptive_threshold_multiplier", 1.5),
            "wake_word.adaptive_threshold_multiplier",
        ),
        validate_paths=_as_bool(
            wake_raw.get("validate_paths", True),
            "wake_word.validate_paths",
        ),
    )

    stt_raw = _section(raw, "stt")
    stt = STTSettings(
        model_size=_as_str(stt_raw.get("model_size", "base"), "stt.model_size"),
        device=_as_str(stt_raw.get("device", "cpu"), "stt.device"),
        compute_type=_as_str(
            stt_raw.get("compute_type", "int8"),
            "stt.compute_type",
        ),
        language=_as_optional_str(stt_raw.get("language", "en"), "stt.language"),
        beam_size=_as_int(stt_raw.get("beam_size", 5), "stt.beam_size"),
        vad_filter=_as_bool(stt_raw.get("vad_filter", True), "stt.vad_filter"),
    )

    tts_raw = _section(raw, "tts")
    tts = TTSSettings(
        enabled=_as_bool(tts_raw.get("enabled", False), "tts.enabled"),
        model_path=_resolve_path(
            base_dir,
            _as_str(tts_raw.get("model_path", ""), "tts.model_path"),
        ),
        config_path=_resolve_path(
            base_dir,
            _as_str(tts_raw.get("config_path", ""), "tts.config_path"),
        ),
        gpu=_as_bool(tts_raw.get("gpu", False), "tts.gpu"),
        output_device=(
            _as_int(tts_raw.get("output_device"), "tts.output_device")
            if "output_device" in tts_raw
            else None
        ),
    )

    llm_raw = _section(raw, "llm")
    system_prompt = _as_str(llm_raw.get("system_prompt", ""), "llm.system_prompt")
    llm = LLMSettings(
        enabled=_as_bool(llm_raw.get("enabled", False), "llm.enabled"),
        model_path=_resolve_path(
            base_dir,
            _as_str(llm_raw.get("model_path", ""), "llm.model_path"),
        ),
        hf_filename=_as_str(llm_raw.get("hf_filename", ""), "llm.hf_filename"),
        hf_repo_id=_as_str(llm_raw.get("hf_repo_id", ""), "llm.hf_repo_id"),
        hf_revision=_as_str(llm_raw.get("hf_revision", ""), "llm.hf_revision"),
        system_prompt=_resolve_path(base_dir, system_prompt) if system_prompt else "",
        n_threads=_as_int(llm_raw.get("n_threads", 4), "llm.n_threads"),
        n_ctx=_as_int(llm_raw.get("n_ctx", 2048), "llm.n_ctx"),
        n_batch=_as_int(llm_raw.get("n_batch", 256), "llm.n_batch"),
        temperature=_as_float(llm_raw.get("temperature", 0.2), "llm.temperature"),
        top_p=_as_float(llm_raw.get("top_p", 0.9), "llm.top_p"),
        repeat_penalty=_as_float(
            llm_raw.get("repeat_penalty", 1.1),
            "llm.repeat_penalty",
        ),
        verbose=_as_bool(llm_raw.get("verbose", False), "llm.verbose"),
    )

    ui_raw = _section(raw, "ui_server")
    index_file = _as_str(ui_raw.get("index_file", ""), "ui_server.index_file")
    ui_server = UIServerSettings(
        enabled=_as_bool(ui_raw.get("enabled", True), "ui_server.enabled"),
        host=_as_str(ui_raw.get("host", "127.0.0.1"), "ui_server.host"),
        port=_as_int(ui_raw.get("port", 8765), "ui_server.port"),
        ws_path=_as_str(ui_raw.get("ws_path", "/ws"), "ui_server.ws_path"),
        index_file=_resolve_path(base_dir, index_file) if index_file else "",
    )

    oracle_raw = _section(raw, "oracle")
    _forbid_secret_fields(
        oracle_raw,
        "oracle",
        ("google_calendar_id", "google_service_account_file"),
    )
    oracle = OracleSettings(
        enabled=_as_bool(oracle_raw.get("enabled", True), "oracle.enabled"),
        ens160_enabled=_as_bool(
            oracle_raw.get("ens160_enabled", False),
            "oracle.ens160_enabled",
        ),
        temt6000_enabled=_as_bool(
            oracle_raw.get("temt6000_enabled", False),
            "oracle.temt6000_enabled",
        ),
        google_calendar_enabled=_as_bool(
            oracle_raw.get("google_calendar_enabled", False),
            "oracle.google_calendar_enabled",
        ),
        google_calendar_max_results=_as_int(
            oracle_raw.get("google_calendar_max_results", 5),
            "oracle.google_calendar_max_results",
        ),
        sensor_cache_ttl_seconds=_as_float(
            oracle_raw.get("sensor_cache_ttl_seconds", 15.0),
            "oracle.sensor_cache_ttl_seconds",
        ),
        calendar_cache_ttl_seconds=_as_float(
            oracle_raw.get("calendar_cache_ttl_seconds", 60.0),
            "oracle.calendar_cache_ttl_seconds",
        ),
        ens160_temperature_compensation_c=_as_float(
            oracle_raw.get("ens160_temperature_compensation_c", 25.0),
            "oracle.ens160_temperature_compensation_c",
        ),
        ens160_humidity_compensation_pct=_as_float(
            oracle_raw.get("ens160_humidity_compensation_pct", 50.0),
            "oracle.ens160_humidity_compensation_pct",
        ),
        temt6000_channel=_as_int(
            oracle_raw.get("temt6000_channel", 0),
            "oracle.temt6000_channel",
        ),
        temt6000_gain=_as_int(
            oracle_raw.get("temt6000_gain", 1),
            "oracle.temt6000_gain",
        ),
        temt6000_adc_address=_as_int(
            oracle_raw.get("temt6000_adc_address", 0x48),
            "oracle.temt6000_adc_address",
        ),
        temt6000_busnum=_as_int(
            oracle_raw.get("temt6000_busnum", 1),
            "oracle.temt6000_busnum",
        ),
    )

    return AppConfig(
        wake_word=wake_word,
        stt=stt,
        tts=tts,
        llm=llm,
        ui_server=ui_server,
        oracle=oracle,
        source_file=str(path),
    )


def load_secret_config(
    *,
    environ: Mapping[str, str] | None = None,
) -> SecretConfig:
    env = environ if environ is not None else os.environ
    pico = env.get("PICO_VOICE_ACCESS_KEY", "").strip()
    if not pico:
        raise AppConfigurationError(
            "PICO_VOICE_ACCESS_KEY must be set as an environment secret."
        )

    hf_token = env.get("HF_TOKEN", "").strip() or None
    calendar_id = env.get("ORACLE_GOOGLE_CALENDAR_ID", "").strip() or None
    service_account = (
        env.get("ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE", "").strip() or None
    )
    return SecretConfig(
        pico_voice_access_key=pico,
        hf_token=hf_token,
        oracle_google_calendar_id=calendar_id,
        oracle_google_service_account_file=service_account,
    )


def _section(root: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    raw = root.get(name, {})
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise AppConfigurationError(f"[{name}] must be a table.")
    return raw


def _required_str(section: Mapping[str, Any], field: str, section_name: str) -> str:
    value = section.get(field)
    text = _as_str(value, f"{section_name}.{field}")
    if not text:
        raise AppConfigurationError(f"{section_name}.{field} is required.")
    return text


def _as_str(value: Any, field: str) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    raise AppConfigurationError(f"{field} must be a string.")


def _as_optional_str(value: Any, field: str) -> Optional[str]:
    text = _as_str(value, field)
    if not text:
        return None
    return text


def _as_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    raise AppConfigurationError(f"{field} must be a boolean.")


def _as_int(value: Any, field: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        base = 16 if text.startswith("0x") else 10
        try:
            return int(text, base)
        except ValueError as error:
            raise AppConfigurationError(f"{field} must be an integer.") from error
    raise AppConfigurationError(f"{field} must be an integer.")


def _as_float(value: Any, field: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as error:
            raise AppConfigurationError(f"{field} must be a float.") from error
    raise AppConfigurationError(f"{field} must be a float.")


def _resolve_path(base_dir: Path, raw: str) -> str:
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return str(path)


def _forbid_secret_fields(
    section: Mapping[str, Any],
    section_name: str,
    fields: tuple[str, ...],
) -> None:
    present = [field for field in fields if field in section]
    if present:
        joined = ", ".join(f"{section_name}.{field}" for field in present)
        raise AppConfigurationError(
            f"Secret values must not be stored in config.toml: {joined}. "
            "Move them to environment variables."
        )

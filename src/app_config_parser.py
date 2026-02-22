"""Typed parser for config.toml sections into immutable app settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from app_config_schema import (
    AppConfig,
    AppConfigurationError,
    LLMSettings,
    OracleSettings,
    STTSettings,
    TTSSettings,
    UIServerSettings,
    WakeWordSettings,
)

_ALLOWED_UI_VARIANTS = {"jarvis", "miro"}


def parse_app_config(
    raw: Mapping[str, Any],
    *,
    base_dir: Path,
    source_file: str,
) -> AppConfig:
    """Parse raw TOML mappings into strongly typed application settings."""
    wake_word = _parse_wake_word_settings(_section(raw, "wake_word"), base_dir=base_dir)
    stt = _parse_stt_settings(_section(raw, "stt"))
    tts = _parse_tts_settings(_section(raw, "tts"), base_dir=base_dir)
    llm = _parse_llm_settings(_section(raw, "llm"), base_dir=base_dir)
    ui_server = _parse_ui_server_settings(_section(raw, "ui_server"), base_dir=base_dir)
    oracle = _parse_oracle_settings(_section(raw, "oracle"))

    return AppConfig(
        wake_word=wake_word,
        stt=stt,
        tts=tts,
        llm=llm,
        ui_server=ui_server,
        oracle=oracle,
        source_file=source_file,
    )


def _parse_wake_word_settings(
    section: Mapping[str, Any],
    *,
    base_dir: Path,
) -> WakeWordSettings:
    ppn_file = _required_str(section, "ppn_file", "wake_word")
    pv_file = _required_str(section, "pv_file", "wake_word")
    return WakeWordSettings(
        ppn_file=_resolve_path(base_dir, ppn_file),
        pv_file=_resolve_path(base_dir, pv_file),
        device_index=_as_int(section.get("device_index", 0), "wake_word.device_index"),
        silence_timeout_seconds=_as_float(
            section.get("silence_timeout_seconds", 1.5),
            "wake_word.silence_timeout_seconds",
        ),
        max_utterance_seconds=_as_float(
            section.get("max_utterance_seconds", 10.0),
            "wake_word.max_utterance_seconds",
        ),
        no_speech_timeout_seconds=_as_float(
            section.get("no_speech_timeout_seconds", 3.0),
            "wake_word.no_speech_timeout_seconds",
        ),
        min_speech_seconds=_as_float(
            section.get("min_speech_seconds", 0.15),
            "wake_word.min_speech_seconds",
        ),
        energy_threshold=_as_float(
            section.get("energy_threshold", 100.0),
            "wake_word.energy_threshold",
        ),
        noise_floor_calibration_seconds=_as_float(
            section.get("noise_floor_calibration_seconds", 1.0),
            "wake_word.noise_floor_calibration_seconds",
        ),
        adaptive_threshold_multiplier=_as_float(
            section.get("adaptive_threshold_multiplier", 1.5),
            "wake_word.adaptive_threshold_multiplier",
        ),
        validate_paths=_as_bool(
            section.get("validate_paths", True),
            "wake_word.validate_paths",
        ),
    )


def _parse_stt_settings(section: Mapping[str, Any]) -> STTSettings:
    return STTSettings(
        model_size=_as_str(section.get("model_size", "base"), "stt.model_size"),
        device=_as_str(section.get("device", "cpu"), "stt.device"),
        compute_type=_as_str(
            section.get("compute_type", "int8"),
            "stt.compute_type",
        ),
        language=_as_optional_str(section.get("language", "en"), "stt.language"),
        beam_size=_as_int(section.get("beam_size", 5), "stt.beam_size"),
        vad_filter=_as_bool(section.get("vad_filter", True), "stt.vad_filter"),
    )


def _parse_tts_settings(
    section: Mapping[str, Any],
    *,
    base_dir: Path,
) -> TTSSettings:
    return TTSSettings(
        enabled=_as_bool(section.get("enabled", False), "tts.enabled"),
        model_path=_resolve_path(
            base_dir,
            _as_str(section.get("model_path", ""), "tts.model_path"),
        ),
        hf_filename=_as_str(section.get("hf_filename", ""), "tts.hf_filename"),
        hf_repo_id=_as_str(section.get("hf_repo_id", ""), "tts.hf_repo_id"),
        hf_revision=(
            _as_str(section.get("hf_revision", "main"), "tts.hf_revision") or "main"
        ),
        gpu=_as_bool(section.get("gpu", False), "tts.gpu"),
        output_device=(
            _as_int(section.get("output_device"), "tts.output_device")
            if "output_device" in section
            else None
        ),
    )


def _parse_llm_settings(
    section: Mapping[str, Any],
    *,
    base_dir: Path,
) -> LLMSettings:
    system_prompt = _as_str(section.get("system_prompt", ""), "llm.system_prompt")
    return LLMSettings(
        enabled=_as_bool(section.get("enabled", False), "llm.enabled"),
        model_path=_resolve_path(
            base_dir,
            _as_str(section.get("model_path", ""), "llm.model_path"),
        ),
        hf_filename=_as_str(section.get("hf_filename", ""), "llm.hf_filename"),
        hf_repo_id=_as_str(section.get("hf_repo_id", ""), "llm.hf_repo_id"),
        hf_revision=_as_str(section.get("hf_revision", ""), "llm.hf_revision"),
        system_prompt=_resolve_path(base_dir, system_prompt) if system_prompt else "",
        n_threads=_as_int(section.get("n_threads", 4), "llm.n_threads"),
        n_ctx=_as_int(section.get("n_ctx", 2048), "llm.n_ctx"),
        n_batch=_as_int(section.get("n_batch", 256), "llm.n_batch"),
        temperature=_as_float(section.get("temperature", 0.2), "llm.temperature"),
        top_p=_as_float(section.get("top_p", 0.9), "llm.top_p"),
        repeat_penalty=_as_float(
            section.get("repeat_penalty", 1.1),
            "llm.repeat_penalty",
        ),
        verbose=_as_bool(section.get("verbose", False), "llm.verbose"),
    )


def _parse_ui_server_settings(
    section: Mapping[str, Any],
    *,
    base_dir: Path,
) -> UIServerSettings:
    ui = _as_ui_name(section.get("ui", "jarvis"), "ui_server.ui")
    index_file = _as_str(section.get("index_file", ""), "ui_server.index_file")
    return UIServerSettings(
        enabled=_as_bool(section.get("enabled", True), "ui_server.enabled"),
        host=_as_str(section.get("host", "127.0.0.1"), "ui_server.host"),
        port=_as_int(section.get("port", 8765), "ui_server.port"),
        ui=ui,
        index_file=_resolve_path(base_dir, index_file) if index_file else "",
    )


def _parse_oracle_settings(section: Mapping[str, Any]) -> OracleSettings:
    _forbid_secret_fields(
        section,
        "oracle",
        ("google_calendar_id", "google_service_account_file"),
    )
    return OracleSettings(
        enabled=_as_bool(section.get("enabled", True), "oracle.enabled"),
        ens160_enabled=_as_bool(
            section.get("ens160_enabled", False),
            "oracle.ens160_enabled",
        ),
        temt6000_enabled=_as_bool(
            section.get("temt6000_enabled", False),
            "oracle.temt6000_enabled",
        ),
        google_calendar_enabled=_as_bool(
            section.get("google_calendar_enabled", False),
            "oracle.google_calendar_enabled",
        ),
        google_calendar_max_results=_as_int(
            section.get("google_calendar_max_results", 5),
            "oracle.google_calendar_max_results",
        ),
        sensor_cache_ttl_seconds=_as_float(
            section.get("sensor_cache_ttl_seconds", 15.0),
            "oracle.sensor_cache_ttl_seconds",
        ),
        calendar_cache_ttl_seconds=_as_float(
            section.get("calendar_cache_ttl_seconds", 60.0),
            "oracle.calendar_cache_ttl_seconds",
        ),
        ens160_temperature_compensation_c=_as_float(
            section.get("ens160_temperature_compensation_c", 25.0),
            "oracle.ens160_temperature_compensation_c",
        ),
        ens160_humidity_compensation_pct=_as_float(
            section.get("ens160_humidity_compensation_pct", 50.0),
            "oracle.ens160_humidity_compensation_pct",
        ),
        temt6000_channel=_as_int(
            section.get("temt6000_channel", 0),
            "oracle.temt6000_channel",
        ),
        temt6000_gain=_as_int(
            section.get("temt6000_gain", 1),
            "oracle.temt6000_gain",
        ),
        temt6000_adc_address=_as_int(
            section.get("temt6000_adc_address", 0x48),
            "oracle.temt6000_adc_address",
        ),
        temt6000_busnum=_as_int(
            section.get("temt6000_busnum", 1),
            "oracle.temt6000_busnum",
        ),
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


def _as_ui_name(value: Any, field: str) -> str:
    name = _as_str(value, field).lower()
    if name not in _ALLOWED_UI_VARIANTS:
        allowed = ", ".join(sorted(_ALLOWED_UI_VARIANTS))
        raise AppConfigurationError(f"{field} must be one of: {allowed}.")
    return name


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

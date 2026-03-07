"""Typed parser for config.toml sections into immutable app settings."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Mapping

from .schema import (
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
_ALLOWED_LLM_AFFINITY_MODES = {"pinned", "shared"}


def parse_app_config(
    content: bytes,
    *,
    base_dir: Path,
    source_file: str,
) -> AppConfig:
    """Parse raw TOML bytes into strongly typed application settings."""
    try:
        raw: Mapping[str, Any] = tomllib.loads(content.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise AppConfigurationError(f"Failed to parse config TOML: {error}") from error

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
        device_index=_as_int(
            section.get("device_index", WakeWordSettings.device_index),
            "wake_word.device_index",
        ),
        silence_timeout_seconds=_as_float(
            section.get(
                "silence_timeout_seconds",
                WakeWordSettings.silence_timeout_seconds,
            ),
            "wake_word.silence_timeout_seconds",
        ),
        max_utterance_seconds=_as_float(
            section.get(
                "max_utterance_seconds",
                WakeWordSettings.max_utterance_seconds,
            ),
            "wake_word.max_utterance_seconds",
        ),
        no_speech_timeout_seconds=_as_float(
            section.get(
                "no_speech_timeout_seconds",
                WakeWordSettings.no_speech_timeout_seconds,
            ),
            "wake_word.no_speech_timeout_seconds",
        ),
        min_speech_seconds=_as_float(
            section.get(
                "min_speech_seconds",
                WakeWordSettings.min_speech_seconds,
            ),
            "wake_word.min_speech_seconds",
        ),
        energy_threshold=_as_float(
            section.get("energy_threshold", WakeWordSettings.energy_threshold),
            "wake_word.energy_threshold",
        ),
        noise_floor_calibration_seconds=_as_float(
            section.get(
                "noise_floor_calibration_seconds",
                WakeWordSettings.noise_floor_calibration_seconds,
            ),
            "wake_word.noise_floor_calibration_seconds",
        ),
        adaptive_threshold_multiplier=_as_float(
            section.get(
                "adaptive_threshold_multiplier",
                WakeWordSettings.adaptive_threshold_multiplier,
            ),
            "wake_word.adaptive_threshold_multiplier",
        ),
        validate_paths=_as_bool(
            section.get("validate_paths", WakeWordSettings.validate_paths),
            "wake_word.validate_paths",
        ),
    )


def _parse_stt_settings(section: Mapping[str, Any]) -> STTSettings:
    return STTSettings(
        model_size=_as_str(section.get("model_size", STTSettings.model_size), "stt.model_size"),
        device=_as_str(section.get("device", STTSettings.device), "stt.device"),
        compute_type=_as_str(
            section.get("compute_type", STTSettings.compute_type),
            "stt.compute_type",
        ),
        language=(
            _as_str(section.get("language", STTSettings.language), "stt.language") or None
        ),
        beam_size=_as_int(section.get("beam_size", STTSettings.beam_size), "stt.beam_size"),
        vad_filter=_as_bool(section.get("vad_filter", STTSettings.vad_filter), "stt.vad_filter"),
        cpu_threads=_as_int(
            section.get("cpu_threads", STTSettings.cpu_threads),
            "stt.cpu_threads",
        ),
        cpu_cores=_as_int_tuple(section.get("cpu_cores", STTSettings.cpu_cores), "stt.cpu_cores"),
    )


def _parse_tts_settings(
    section: Mapping[str, Any],
    *,
    base_dir: Path,
) -> TTSSettings:
    return TTSSettings(
        enabled=_as_bool(section.get("enabled", TTSSettings.enabled), "tts.enabled"),
        model_path=_resolve_path(
            base_dir,
            _as_str(section.get("model_path", TTSSettings.model_path), "tts.model_path"),
        ),
        hf_filename=_as_str(section.get("hf_filename", TTSSettings.hf_filename), "tts.hf_filename"),
        hf_repo_id=_as_str(section.get("hf_repo_id", TTSSettings.hf_repo_id), "tts.hf_repo_id"),
        hf_revision=(
            _as_str(section.get("hf_revision", TTSSettings.hf_revision), "tts.hf_revision")
            or TTSSettings.hf_revision
        ),
        gpu=_as_bool(section.get("gpu", TTSSettings.gpu), "tts.gpu"),
        output_device=(
            _as_int(section.get("output_device"), "tts.output_device")
            if "output_device" in section
            else None
        ),
        cpu_cores=_as_int_tuple(section.get("cpu_cores", TTSSettings.cpu_cores), "tts.cpu_cores"),
    )


def _parse_llm_settings(
    section: Mapping[str, Any],
    *,
    base_dir: Path,
) -> LLMSettings:
    system_prompt = _as_str(
        section.get("system_prompt", LLMSettings.system_prompt),
        "llm.system_prompt",
    )
    max_tokens = (
        _as_int(section.get("max_tokens"), "llm.max_tokens")
        if "max_tokens" in section
        else None
    )
    return LLMSettings(
        enabled=_as_bool(section.get("enabled", LLMSettings.enabled), "llm.enabled"),
        model_path=_resolve_path(
            base_dir,
            _as_str(section.get("model_path", LLMSettings.model_path), "llm.model_path"),
        ),
        hf_filename=_as_str(section.get("hf_filename", LLMSettings.hf_filename), "llm.hf_filename"),
        hf_repo_id=_as_str(section.get("hf_repo_id", LLMSettings.hf_repo_id), "llm.hf_repo_id"),
        hf_revision=_as_str(section.get("hf_revision", LLMSettings.hf_revision), "llm.hf_revision"),
        system_prompt=_resolve_path(base_dir, system_prompt) if system_prompt else "",
        max_tokens=max_tokens,
        n_threads=_as_int(section.get("n_threads", LLMSettings.n_threads), "llm.n_threads"),
        n_ctx=_as_int(section.get("n_ctx", LLMSettings.n_ctx), "llm.n_ctx"),
        n_batch=_as_int(section.get("n_batch", LLMSettings.n_batch), "llm.n_batch"),
        temperature=_as_float(
            section.get("temperature", LLMSettings.temperature),
            "llm.temperature",
        ),
        top_p=_as_float(section.get("top_p", LLMSettings.top_p), "llm.top_p"),
        top_k=_as_int(section.get("top_k", LLMSettings.top_k), "llm.top_k"),
        min_p=_as_float(section.get("min_p", LLMSettings.min_p), "llm.min_p"),
        repeat_penalty=_as_float(
            section.get("repeat_penalty", LLMSettings.repeat_penalty),
            "llm.repeat_penalty",
        ),
        n_threads_batch=(
            _as_int(
                section.get("n_threads_batch"),
                "llm.n_threads_batch",
            )
            if "n_threads_batch" in section
            else None
        ),
        n_ubatch=(
            _as_int(section.get("n_ubatch"), "llm.n_ubatch")
            if "n_ubatch" in section
            else None
        ),
        use_mmap=_as_bool(section.get("use_mmap", LLMSettings.use_mmap), "llm.use_mmap"),
        use_mlock=_as_bool(
            section.get("use_mlock", LLMSettings.use_mlock),
            "llm.use_mlock",
        ),
        verbose=_as_bool(section.get("verbose", LLMSettings.verbose), "llm.verbose"),
        fast_path_enabled=_as_bool(
            section.get("fast_path_enabled", LLMSettings.fast_path_enabled),
            "llm.fast_path_enabled",
        ),
        cpu_affinity_mode=_as_llm_affinity_mode(
            section.get("cpu_affinity_mode", LLMSettings.cpu_affinity_mode),
            "llm.cpu_affinity_mode",
        ),
        shared_cpu_reserve_cores=_as_int(
            section.get(
                "shared_cpu_reserve_cores",
                LLMSettings.shared_cpu_reserve_cores,
            ),
            "llm.shared_cpu_reserve_cores",
        ),
        cpu_cores=_as_int_tuple(section.get("cpu_cores", LLMSettings.cpu_cores), "llm.cpu_cores"),
    )


def _parse_ui_server_settings(
    section: Mapping[str, Any],
    *,
    base_dir: Path,
) -> UIServerSettings:
    ui = _as_ui_name(section.get("ui", UIServerSettings.ui), "ui_server.ui")
    index_file = _as_str(
        section.get("index_file", UIServerSettings.index_file),
        "ui_server.index_file",
    )
    return UIServerSettings(
        enabled=_as_bool(section.get("enabled", UIServerSettings.enabled), "ui_server.enabled"),
        host=_as_str(section.get("host", UIServerSettings.host), "ui_server.host"),
        port=_as_int(section.get("port", UIServerSettings.port), "ui_server.port"),
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
        enabled=_as_bool(section.get("enabled", OracleSettings.enabled), "oracle.enabled"),
        ens160_enabled=_as_bool(
            section.get("ens160_enabled", OracleSettings.ens160_enabled),
            "oracle.ens160_enabled",
        ),
        temt6000_enabled=_as_bool(
            section.get("temt6000_enabled", OracleSettings.temt6000_enabled),
            "oracle.temt6000_enabled",
        ),
        google_calendar_enabled=_as_bool(
            section.get(
                "google_calendar_enabled",
                OracleSettings.google_calendar_enabled,
            ),
            "oracle.google_calendar_enabled",
        ),
        google_calendar_max_results=_as_int(
            section.get(
                "google_calendar_max_results",
                OracleSettings.google_calendar_max_results,
            ),
            "oracle.google_calendar_max_results",
        ),
        sensor_cache_ttl_seconds=_as_float(
            section.get(
                "sensor_cache_ttl_seconds",
                OracleSettings.sensor_cache_ttl_seconds,
            ),
            "oracle.sensor_cache_ttl_seconds",
        ),
        calendar_cache_ttl_seconds=_as_float(
            section.get(
                "calendar_cache_ttl_seconds",
                OracleSettings.calendar_cache_ttl_seconds,
            ),
            "oracle.calendar_cache_ttl_seconds",
        ),
        ens160_temperature_compensation_c=_as_float(
            section.get(
                "ens160_temperature_compensation_c",
                OracleSettings.ens160_temperature_compensation_c,
            ),
            "oracle.ens160_temperature_compensation_c",
        ),
        ens160_humidity_compensation_pct=_as_float(
            section.get(
                "ens160_humidity_compensation_pct",
                OracleSettings.ens160_humidity_compensation_pct,
            ),
            "oracle.ens160_humidity_compensation_pct",
        ),
        temt6000_channel=_as_int(
            section.get("temt6000_channel", OracleSettings.temt6000_channel),
            "oracle.temt6000_channel",
        ),
        temt6000_gain=_as_int(
            section.get("temt6000_gain", OracleSettings.temt6000_gain),
            "oracle.temt6000_gain",
        ),
        temt6000_adc_address=_as_int(
            section.get("temt6000_adc_address", OracleSettings.temt6000_adc_address),
            "oracle.temt6000_adc_address",
        ),
        temt6000_busnum=_as_int(
            section.get("temt6000_busnum", OracleSettings.temt6000_busnum),
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


def _as_int_tuple(value: Any, field: str) -> tuple[int, ...]:
    if value is None:
        return ()

    if isinstance(value, tuple):
        sequence = value
    elif isinstance(value, list):
        sequence = tuple(value)
    else:
        raise AppConfigurationError(f"{field} must be an array of integers.")

    parsed: list[int] = []
    seen: set[int] = set()
    for index, raw in enumerate(sequence):
        core = _as_int(raw, f"{field}[{index}]")
        if core < 0:
            raise AppConfigurationError(f"{field}[{index}] must be >= 0.")
        if core in seen:
            raise AppConfigurationError(f"{field} cannot contain duplicates.")
        seen.add(core)
        parsed.append(core)

    return tuple(parsed)


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


def _as_llm_affinity_mode(value: Any, field: str) -> str:
    mode = _as_str(value, field).lower()
    if mode not in _ALLOWED_LLM_AFFINITY_MODES:
        allowed = ", ".join(sorted(_ALLOWED_LLM_AFFINITY_MODES))
        raise AppConfigurationError(f"{field} must be one of: {allowed}.")
    return mode


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

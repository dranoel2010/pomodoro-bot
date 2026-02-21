from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping

from app_config_parser import parse_app_config
from app_config_schema import (
    AppConfig,
    AppConfigurationError,
    DEFAULT_CONFIG_FILE,
    LLMSettings,
    OracleSettings,
    STTSettings,
    SecretConfig,
    TTSSettings,
    UIServerSettings,
    WakeWordSettings,
)

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older runtimes
    import tomli as tomllib  # type: ignore


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

    return parse_app_config(
        raw,
        base_dir=path.parent,
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


__all__ = [
    "AppConfig",
    "AppConfigurationError",
    "DEFAULT_CONFIG_FILE",
    "LLMSettings",
    "OracleSettings",
    "STTSettings",
    "SecretConfig",
    "TTSSettings",
    "UIServerSettings",
    "WakeWordSettings",
    "load_app_config",
    "load_secret_config",
    "resolve_config_path",
]

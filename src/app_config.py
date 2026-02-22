"""Configuration loading helpers for app settings and environment secrets."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping

from shared.env_keys import (
    ENV_APP_CONFIG_FILE,
    ENV_HF_TOKEN,
    ENV_ORACLE_GOOGLE_CALENDAR_ID,
    ENV_ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE,
    ENV_PICO_VOICE_ACCESS_KEY,
)

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
    """Resolve the config file path from argument, environment, or default location."""
    env_path = os.getenv(ENV_APP_CONFIG_FILE)
    raw = config_path or env_path or DEFAULT_CONFIG_FILE
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path

    cwd_path = (Path.cwd() / path).resolve()
    if cwd_path.exists():
        return cwd_path

    # In frozen mode with default config name, prefer config beside the executable.
    if config_path is None and env_path is None and getattr(sys, "frozen", False):
        executable_path = (
            Path(sys.executable).resolve().parent / DEFAULT_CONFIG_FILE
        ).resolve()
        return executable_path

    return cwd_path


def load_app_config(config_path: str | None = None) -> AppConfig:
    """Load and parse TOML config into a validated `AppConfig` instance."""
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
    """Load required secrets from environment variables into `SecretConfig`."""
    env = environ if environ is not None else os.environ
    pico = env.get(ENV_PICO_VOICE_ACCESS_KEY, "").strip()
    if not pico:
        raise AppConfigurationError(
            f"{ENV_PICO_VOICE_ACCESS_KEY} must be set as an environment secret."
        )

    hf_token = env.get(ENV_HF_TOKEN, "").strip() or None
    calendar_id = env.get(ENV_ORACLE_GOOGLE_CALENDAR_ID, "").strip() or None
    service_account = (
        env.get(ENV_ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE, "").strip() or None
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

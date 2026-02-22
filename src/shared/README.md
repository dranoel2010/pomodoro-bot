# shared module

## Purpose
Central location for cross-cutting defaults and environment key constants.

## Key files
- `defaults.py`: default timer/calendar/focus text values used by runtime and parser logic.
- `env_keys.py`: canonical names for environment variables used by config loading.

## Configuration
No direct configuration.
This module only defines constants consumed elsewhere.

## Integration notes
- Imported by `app_config`, `llm`, and `runtime` modules to avoid duplicated literals.

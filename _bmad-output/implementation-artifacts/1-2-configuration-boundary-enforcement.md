# Story 1.2: Configuration Boundary Enforcement

Status: done

## Story

As a developer,
I want the three config files to have explicit, non-overlapping responsibilities with no I/O in schema or parser files,
so that config logic has a single owner and I can navigate config concerns without confusion about which file is authoritative.

## Acceptance Criteria

1. **Given** `app_config_schema.py`, `app_config_parser.py`, and `app_config.py` exist
   **When** the boundary enforcement is complete
   **Then** `app_config_schema.py` contains only pure dataclasses (`AppConfig`, `SecretConfig`, `*Settings`) with zero I/O — no file reads, no `os.getenv` calls
   **And** `app_config_parser.py` contains only the TOML bytes → typed config logic with zero I/O — accepts `bytes`, returns typed config, no file reads
   **And** `app_config.py` is the sole location for all I/O: file reading, `os.getenv`, `PICO_VOICE_ACCESS_KEY` loading, and the `getattr(sys, "frozen", False)` frozen-binary guard

2. **Given** the CPU core assignment configuration exists
   **When** a developer reads `config.toml`
   **Then** `[stt] cpu_cores`, `[llm] cpu_cores`, and `[tts] cpu_cores` keys are clearly documented with their defaults
   **And** the `APP_CONFIG_FILE` environment variable override is respected — the system loads config from the path specified in that variable when set

3. **Given** the boundary enforcement is complete
   **When** `uv run pytest tests/` is executed
   **Then** all tests pass with no regressions

## Tasks / Subtasks

- [x] Change `app_config_parser.py` to accept `bytes` (AC: #1)
  - [x] Change `parse_app_config` signature: `raw: Mapping[str, Any]` → `content: bytes`
  - [x] Add `import tomllib` at top of `app_config_parser.py`
  - [x] Inside `parse_app_config`, decode bytes and parse TOML: `raw = tomllib.loads(content.decode())`
  - [x] Wrap TOML parse in try/except raising `AppConfigurationError` on `tomllib.TOMLDecodeError`
  - [x] Keep the `if not isinstance(raw, Mapping)` guard after parsing
  - [x] Keep `from typing import Any, Mapping` — still used internally for `_section()`, `Mapping[str, Any]` params
  - [x] Verify `Path` import stays — still needed for `base_dir: Path` and `_resolve_path`

- [x] Update `app_config.py` to pass bytes to parser (AC: #1)
  - [x] Replace `with open(path, "rb") as fh: raw = tomllib.load(fh)` with `content = path.read_bytes()`
  - [x] Remove the `isinstance(raw, Mapping)` guard from `app_config.py` — it now lives in the parser
  - [x] Change `parse_app_config(raw, ...)` call to `parse_app_config(content, ...)`
  - [x] Wrap `path.read_bytes()` in try/except `OSError` → raise `AppConfigurationError`
  - [x] Remove `import tomllib` from `app_config.py` (moved to parser)
  - [x] Verify `from typing import Mapping` stays — still needed for `load_secret_config` signature
  - [x] Do NOT change `resolve_config_path`, `load_secret_config`, or `__all__`

- [x] Document `cpu_cores` in `config.toml` (AC: #2)
  - [x] Add comment above `[stt] cpu_cores` documenting default `[]` and Pi 5 recommendation
  - [x] Add comment above `[tts] cpu_cores` documenting default `[]` and Pi 5 recommendation
  - [x] Add comment above `[llm] cpu_cores` documenting default `[]` and relationship to `cpu_affinity_mode`

- [x] Run full test suite (AC: #3)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — all pass (5/5)
  - [x] `uv run pytest tests/` — all pass, zero regressions (139/139)

## Dev Notes

### Current State — Exact Violation

**`app_config.py` (current — TOML parsing lives here, must move):**
```python
# Lines ~62-76 in load_app_config — this logic moves to parser
try:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)           # ← TOML parsing moves to parser
except Exception as error:
    raise AppConfigurationError(f"Failed to parse config TOML: {error}") from error

if not isinstance(raw, Mapping):         # ← Mapping guard moves to parser
    raise AppConfigurationError("Root config TOML object must be a table.")

return parse_app_config(
    raw,                                  # ← will become content (bytes)
    base_dir=path.parent,
    source_file=str(path),
)
```

**`app_config_parser.py` (current signature — must change):**
```python
def parse_app_config(
    raw: Mapping[str, Any],              # ← must become content: bytes
    *,
    base_dir: Path,
    source_file: str,
) -> AppConfig:
    ...                                  # rest of function body is UNCHANGED
```

### Target Implementation

**`app_config.py` — new `load_app_config` body:**
```python
def load_app_config(config_path: str | None = None) -> AppConfig:
    """Load and parse TOML config into a validated `AppConfig` instance."""
    path = resolve_config_path(config_path)
    if not path.exists():
        raise AppConfigurationError(f"Config file not found: {path}")
    if not path.is_file():
        raise AppConfigurationError(f"Config path is not a file: {path}")

    try:
        content = path.read_bytes()
    except OSError as error:
        raise AppConfigurationError(f"Failed to read config file: {error}") from error

    return parse_app_config(
        content,
        base_dir=path.parent,
        source_file=str(path),
    )
```

Remove `import tomllib` from `app_config.py` imports. `from typing import Mapping` stays (used by `load_secret_config`).

**`app_config_parser.py` — new `parse_app_config` body:**
```python
import tomllib
# ... other existing imports unchanged ...

def parse_app_config(
    content: bytes,
    *,
    base_dir: Path,
    source_file: str,
) -> AppConfig:
    """Parse raw TOML bytes into strongly typed application settings."""
    try:
        raw: Mapping[str, Any] = tomllib.loads(content.decode())
    except tomllib.TOMLDecodeError as error:
        raise AppConfigurationError(f"Failed to parse config TOML: {error}") from error

    if not isinstance(raw, Mapping):
        raise AppConfigurationError("Root config TOML object must be a table.")

    wake_word = _parse_wake_word_settings(_section(raw, "wake_word"), base_dir=base_dir)
    # ... ALL the rest of the parse_app_config body is IDENTICAL — do not change it
```

All private helpers (`_parse_wake_word_settings`, `_parse_stt_settings`, etc.) are **completely unchanged**.

### File Ownership After This Story

| File | Owns | Must NOT contain |
|---|---|---|
| `app_config_schema.py` | Pure dataclasses: `AppConfig`, `SecretConfig`, `*Settings`, `AppConfigurationError`, `DEFAULT_CONFIG_FILE` | File reads, `os.getenv`, `tomllib` |
| `app_config_parser.py` | `parse_app_config(content: bytes, ...)` → typed config; `tomllib.loads()`; all `_parse_*` helpers | `os.getenv`, `open()`, `path.exists()`, `path.is_file()`, `path.read_bytes()`, `sys.frozen` |
| `app_config.py` | `load_app_config()`, `load_secret_config()`, `resolve_config_path()`; all `os.getenv`, `path.read_bytes()`, `sys.frozen` guard | `tomllib` (moved to parser) |

### config.toml — Required Documentation

Add comments above each `cpu_cores` key in `config.toml`:

```toml
[stt]
# ...existing keys...
# cpu_cores: CPU core(s) to pin the STT worker process to (default: [] — no pinning, OS schedules freely)
# Pi 5 recommended: [0] or [0, 1] — STT runs best isolated from LLM cores
cpu_cores = [0, 1]

[tts]
# ...existing keys...
# cpu_cores: CPU core(s) to pin the TTS worker process to (default: [] — no pinning)
# Pi 5 recommended: [3] or [2, 3] — keep TTS on its own core(s) away from STT and LLM
cpu_cores = [2, 3]

[llm]
# ...existing keys...
# cpu_cores: CPU core(s) available to the LLM worker process (default: [] — no pinning)
# Used when cpu_affinity_mode = "pinned"; ignored in "shared" mode (OS schedules across all non-reserved cores)
# Pi 5 recommended (pinned): [1, 2] — leave core 0 for STT and core 3 for TTS
cpu_cores = [0, 1, 2, 3]
```

### APP_CONFIG_FILE env var — Already Implemented

`resolve_config_path()` already respects `APP_CONFIG_FILE` via `ENV_APP_CONFIG_FILE` from `shared/env_keys.py`. **No change needed here.** The AC is satisfied by the existing implementation.

### Test Impact Analysis

All 9 existing tests in `tests/config/test_app_config_loading.py` call `load_app_config(str(config_path))` which is the **end-to-end entry point**. None directly call `parse_app_config()`. No test code changes are required — all 139 tests should pass without modification after this refactor.

The internal flow changes from:
```
load_app_config → tomllib.load(file) → Mapping → parse_app_config(Mapping)
```
to:
```
load_app_config → path.read_bytes() → bytes → parse_app_config(bytes) → tomllib.loads(bytes)
```
...but from the test's perspective, `load_app_config(path)` still works identically.

### Architecture Compliance Checklist

- `from __future__ import annotations` must be **first line** in any edited module (already present in all three files — do not remove)
- `tomllib` is Python 3.13 stdlib — no new dependency required
- `tomllib.TOMLDecodeError` is the correct exception type for invalid TOML (not `Exception`)
- `_resolve_path()` in `app_config_parser.py` uses `Path.resolve()` — this is acceptable path computation, not file I/O in the context of this story's boundary rule
- Do NOT add `slots=True` to schema dataclasses in this story — that is Story 1.4's scope
- Do NOT change `TOOLS_WITHOUT_ARGUMENTS` or dispatch — not in scope

### Project Structure Notes

- `src/` is on `sys.path` — absolute imports: `from app_config_parser import parse_app_config`
- `tomllib` is stdlib in Python 3.11+; no `uv add` needed
- `tomllib.loads()` accepts `str`, not `bytes` directly — decode first: `content.decode()` (UTF-8 is TOML default)
- `tomllib.TOMLDecodeError` is the parse error class (not `ValueError` or `Exception`)

### References

- Epics file: `_bmad-output/planning-artifacts/epics.md` — Story 1.2 acceptance criteria
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — "Config Boundary" section, "Config Ownership Boundaries made explicit"
- Current `src/app_config.py` — lines 55–76 (`load_app_config`) are the primary change target
- Current `src/app_config_parser.py` — lines 23–45 (`parse_app_config` signature + entry) are the primary change target
- Current `src/app_config_schema.py` — **no changes required**
- Implementation sequence note: This is Step 3 of 8 in Phase 1. It follows Story 1.1 (contracts consolidation — done) and precedes 1.3 (LLM module boundaries).

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No debug issues encountered. Implementation was straightforward — the existing test suite exercises the full `load_app_config` end-to-end path, so no test code changes were required.

### Completion Notes List

- Moved `import tomllib` from `app_config.py` to `app_config_parser.py` — `tomllib` now owned exclusively by the parser
- Changed `parse_app_config` signature from `raw: Mapping[str, Any]` to `content: bytes`; TOML decoding and `isinstance(raw, Mapping)` guard moved inside the parser
- `app_config.py` now calls `path.read_bytes()` wrapped in `OSError` guard and passes raw bytes to the parser
- `from typing import Mapping` retained in `app_config.py` — still needed for `load_secret_config(environ: Mapping[str, str] | None = None)` signature
- Added `cpu_cores` entries with documentation comments to `dist/config.toml` for `[stt]`, `[tts]`, and `[llm]` sections; all default to `[]` (no pinning)
- All 139 tests pass with zero regressions

### File List

- `src/app_config_parser.py` (modified)
- `src/app_config.py` (modified)
- `dist/config.toml` (modified — gitignored; changes tracked in `config.toml.example`)
- `config.toml.example` (created — tracked template with cpu_cores documentation)
- `tests/config/test_app_config_parser.py` (created — direct unit tests for parse_app_config bytes interface)

## Change Log

- 2026-02-28: Refactored config boundary — moved TOML parsing from `app_config.py` into `app_config_parser.py`; `parse_app_config` now accepts `bytes`, `app_config.py` uses `path.read_bytes()`; documented `cpu_cores` in `dist/config.toml`
- 2026-02-28: Code review fixes — caught `UnicodeDecodeError` in parser error boundary; removed unreachable `isinstance(raw, Mapping)` guard; fixed PEP 8 blank line in `app_config.py`; added `tests/config/test_app_config_parser.py` (6 new tests, 145 total passing); created tracked `config.toml.example` to version-control cpu_cores documentation (dist/ is gitignored)

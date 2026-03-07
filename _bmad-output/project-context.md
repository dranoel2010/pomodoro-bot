---
project_name: 'pomodoro-bot'
user_name: 'Shrink0r'
date: '2026-02-28'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 47
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

| Technology | Version / Detail |
|---|---|
| **Python** | 3.13+ (required) |
| **Package manager** | `uv` (pyproject.toml + uv.lock) |
| **LLM inference** | `llama-cpp-python >= 0.3.16` (local, GGUF models) |
| **STT** | `faster-whisper >= 1.2.1` + `pvporcupine` (wake word) + `pvrecorder` |
| **TTS** | `piper-tts` + `sounddevice >= 0.5.5` |
| **HuggingFace** | `huggingface-hub >= 0.36.2`, `transformers < 5` |
| **Hardware sensors** | `Adafruit-ADS1x15`, `adafruit-blinka`, `adafruit-circuitpython-ens160` |
| **Calendar** | `google-api-python-client >= 2.0.0`, `google-auth >= 2.0.0` |
| **WebSocket UI** | `websockets >= 15.0.1` |
| **Config format** | TOML (stdlib `tomllib`) |
| **Build/packaging** | `pyinstaller` (frozen binary for Raspberry Pi) |
| **Testing** | `pytest` (std `unittest.TestCase` style) |
| **Process isolation** | `multiprocessing` with `spawn` context (never `fork`) |

**Target platform:** Raspberry Pi 5 (ARM64, 4-core) — performance matters.

### Version Constraint Rules

- **`llama-cpp-python`** — Do not bump without verifying the GBNF `grammar=` API still works (changed between 0.2.x and 0.3.x). Also: GGUF metadata schemas change with llama.cpp releases — a bump may refuse to load a previously-working `.gguf` with a cryptic "unsupported metadata version" error. Never change `llama-cpp-python` and the model file in the same step; isolate each variable.
- **`transformers < 5`** — This ceiling is hard. `AutoTokenizer.from_pretrained()` signature and tokenizer JSON schema both changed in v5. Any code touching `transformers` for tokenization will silently produce wrong token counts or crash on model load if this ceiling is removed.
- **`n_threads` must always be explicitly forwarded** — never rely on llama.cpp auto-detection on Pi 5. Defaulting to all 4 cores causes OS scheduling stalls. Always pass `n_threads` through `LLMConfig`.
- **`compute_type` and `device` must be changed together** — `compute_type = "int8"` is correct for Pi 5 CPU (Cortex-A76 via CTranslate2). Do not change `compute_type` without also changing `device`; it is the pairing that is Pi-CPU-specific, not `int8` in isolation.
- **`vad_filter = true` in STT** — Never default `vad_filter = False` in production code paths, factory defaults, or new config schema fields. VAD filtering is latency-critical; disabling it means every silent audio chunk hits Whisper. Disabling in test fixtures is acceptable.
- **pvporcupine `.ppn` and `.pv` model files must match the installed `pvporcupine` version exactly** — proprietary platform-specific binaries; version mismatch causes silent wrong behaviour or crashes. If the `pvporcupine` version in `pyproject.toml` changes, the model files in `models/sst/` must be regenerated from the Picovoice Console for that exact version. The `.ppn` wake-word file is also locale-, accent-, and sensitivity-specific — it cannot be swapped from a different locale build.
- **TTS `output_device`** — Must remain optional/configurable (currently commented out in config). Never hardcode ALSA device indices; they are not stable across reboots on headless Pi.
- **New process workers must compose `_ProcessWorker` from `workers/core.py`** — do not duplicate the process loop pattern. CPU affinity, logging setup, and restart logic are all handled by `_ProcessWorker`; composing it correctly means `_set_process_cpu_affinity()` is called automatically through the right path. Never call `psutil` or `os.sched_setaffinity` directly from a worker module.

---

## Project Structure

```
src/                          ← Added to sys.path; imports use module name directly (no "src." prefix)
  main.py                     ← Entrypoint and composition root
  app_config.py               ← Config loading: TOML → AppConfig, secrets from env vars
  app_config_schema.py        ← AppConfig, SecretConfig, *Settings dataclasses
  app_config_parser.py        ← TOML → typed config parsing
  contracts/
    tool_contract.py          ← SINGLE SOURCE OF TRUTH for all tool names + LLM grammar
    ui_protocol.py            ← All event/state string constants for WebSocket UI
  llm/
    types.py                  ← StructuredResponse, EnvironmentContext, ToolCall, ToolName
    service.py                ← PomodoroAssistantLLM (orchestration entrypoint)
    llama_backend.py          ← llama.cpp wrapper with GBNF grammar-constrained JSON output
    fast_path.py              ← Deterministic command router (bypasses llama.cpp)
    parser.py                 ← JSON normalization + intent fallback behaviour
    model_store.py            ← GGUF download/validation from HuggingFace
    config.py                 ← LLMConfig validated settings
    factory.py                ← create_llm_config() — config assembly only
  stt/
    events.py                 ← Utterance, QueueEventPublisher, event dataclasses
    service.py                ← WakeWordService
    transcription.py          ← TranscriptionResult, STTError
    factory.py
  tts/
    engine.py                 ← TTSError
    service.py, output.py, factory.py
  oracle/
    service.py                ← OracleContextService (env sensor + calendar data)
    providers.py, factory.py
    calendar/google_calendar.py
    sensor/ens160_sensor.py, temt6000_sensor.py
  pomodoro/
    constants.py              ← ACTION_*, REASON_* string constants
    service.py                ← PomodoroTimer
    tool_mapping.py
  server/
    service.py                ← UIServer (WebSocket)
    ui_server.py, factory.py
  shared/
    env_keys.py               ← ENV_* constants for all environment variable names
    defaults.py, spoken_time.py
  runtime/
    __init__.py               ← exports RuntimeEngine only
    engine.py                 ← RuntimeEngine + RuntimeComponents dataclass
    contracts.py              ← STTClient, LLMClient, TTSClient (Protocol interfaces)
    utterance.py              ← process_utterance() — STT→LLM→tool→TTS pipeline
    ticks.py                  ← Pomodoro/timer tick handlers
    ui.py                     ← RuntimeUIPublisher facade
    tools/
      dispatch.py             ← RuntimeToolDispatcher
      messages.py             ← German status/fallback messages
      calendar.py             ← Calendar argument parsing + handlers
    workers/
      core.py                 ← _ProcessWorker, WorkerError hierarchy (shared primitives)
      llm.py                  ← LLMWorker, create_llm_worker()
      stt.py                  ← create_stt_worker()
      tts.py                  ← create_tts_worker()
tests/                        ← Mirrors src/ module structure exactly
  runtime/, llm/, stt/, tts/, oracle/, server/, pomodoro/, config/
```

---

## Critical Implementation Rules

### 1. Import Style

```python
# ALWAYS: from __future__ import annotations at top of every module
from __future__ import annotations

# Imports from within own package: use relative imports
from .config import LLMConfig
from .core import _ProcessWorker

# Cross-package imports: use absolute (src/ is on sys.path, no "src." prefix)
from contracts.tool_contract import TOOL_NAME_ORDER
from llm.types import StructuredResponse
from runtime.contracts import LLMClient

# TYPE_CHECKING guard for type-only imports (avoids circular imports at runtime)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llm.types import EnvironmentContext, StructuredResponse
```

### 2. Tool Names — Never Hardcode

All tool names must come from `src/contracts/tool_contract.py`. **Never define tool names elsewhere**.

```python
# CORRECT
from contracts.tool_contract import TOOL_START_TIMER, TOOL_NAME_ORDER, TOOL_NAMES

# WRONG — never do this
TOOL_START_TIMER = "start_timer"  # hardcoded string
```

`TOOL_NAME_ORDER` is used to generate LLM grammar alternatives (`tool_name_gbnf_alternatives()`) and the `ToolName` Literal type in `llm/types.py`. Adding a new tool requires updating **only** `tool_contract.py`.

### 3. UI Event/State Constants — Never Hardcode

All WebSocket event types and state strings come from `src/contracts/ui_protocol.py`.

```python
# CORRECT
from contracts.ui_protocol import EVENT_ERROR, STATE_IDLE, STATE_THINKING

# WRONG
ui.publish("error", state="idle")  # never use raw strings
```

### 4. multiprocessing — Always Use Spawn Context

```python
# CORRECT
spawn_context = multiprocessing.get_context("spawn")
queue = spawn_context.Queue()
process = spawn_context.Process(...)

# WRONG — fork is unsupported and causes issues with llama.cpp / audio
process = multiprocessing.Process(...)  # uses default (fork on Linux)
```

### 5. Worker Modules — No Mutable Module-Level State (enforced by test)

Worker files (`workers/llm.py`, `workers/stt.py`, `workers/tts.py`) **must not** use:
- `global _variable_name` patterns for shared mutable state
- Module-level `_SOMETHING_INSTANCE` singleton names

The `_process_instance` in `workers/llm.py` is intentional and named as `_process_instance` — not `_INSTANCE`. The test checks for `_\w+_INSTANCE` pattern specifically.

### 6. Runtime Signatures — No `dict[str, object]` (enforced by test)

Functions in `utterance.py`, `tools/dispatch.py`, `tools/calendar.py`, and `ui.py` must use typed contracts or `TypedDict`, not `dict[str, object]`.

```python
# CORRECT
def handle_tool_call(tool_call: ToolCall, assistant_text: str) -> str: ...

# WRONG
def handle_tool_call(tool_call: dict[str, object], ...) -> str: ...
```

### 7. Dataclass Style

```python
# Immutable value objects: frozen=True, slots=True
@dataclass(frozen=True, slots=True)
class LLMPayload:
    user_prompt: str
    env: EnvironmentContext | None = None

# Runtime containers: slots=True
@dataclass(slots=True)
class RuntimeComponents:
    ...
```

### 8. Error Wrapping for Startup

All startup/initialization failures are wrapped in `StartupError` from `contracts/__init__.py`.

```python
from contracts import StartupError

try:
    worker = SomeWorker(...)
except SomeSpecificError as exc:
    raise StartupError(f"Descriptive message: {exc}") from exc
```

### 9. Env Vars — Use Constants from `shared/env_keys.py`

```python
# CORRECT
from shared.env_keys import ENV_HF_TOKEN
token = os.getenv(ENV_HF_TOKEN)

# WRONG
token = os.getenv("HF_TOKEN")  # hardcoded env key name
```

### 10. Language: German Domain, English Code

- All Python identifiers, comments, docstrings: **English**
- All user-facing strings (timer messages, TTS output, date/time formatting, status messages): **German**
- `EnvironmentContext.to_prompt_placeholders()` produces German datetime strings ("Montag", "Januar", etc.)
- Default messages in `runtime/tools/messages.py`: German

### 11. Worker Factory Return Pattern

Worker factory functions return `None` when the component is disabled. Callers check for `None` before use.

```python
assistant_llm = create_llm_worker(...)  # returns LLMWorker | None
if assistant_llm is None and speech_service is not None:
    logger.warning("TTS enabled but LLM disabled; no spoken reply generated.")
```

### 12. Config Access Pattern

Config is a TOML file loaded by `app_config.py`. Secrets come only from environment variables. The single config entry point in `main.py` is `_load_runtime_config()`.

```python
# TOML key: [llm] enabled = true
# Accessed as: app_config.llm.enabled

# Secrets: environment variables only, never in TOML
secret_config.pico_voice_access_key  # from ENV_PICO_VOICE_ACCESS_KEY
secret_config.hf_token               # from ENV_HF_TOKEN (optional)
```

### 13. Unused Parameter Pattern

```python
# Silent unused parameter (linter compliant)
def signal_handler(signum: int, frame: FrameType | None) -> None:
    del frame  # explicitly mark as intentionally unused
```

### 14. Context Manager Support for Workers

Long-lived workers must support the context manager protocol (`__enter__` / `__exit__`).

```python
def __enter__(self) -> LLMWorker:
    return self

def __exit__(self, *_: object) -> None:
    self.close()
```

### 15. Logging Format

All loggers use module-level `logging.getLogger("module.submodule")` pattern. Log format (set in `main.py`):
```
%(asctime)s.%(msecs)03d [%(levelname)s] [%(processName)s:%(process)d] %(name)s: %(message)s
```

Worker processes configure logging via `_configure_worker_logging()` which routes through a `QueueHandler` to the `QueueListener` in the main process.

---

## Testing Patterns

- **Framework:** `pytest` as test runner, `unittest.TestCase` as test class base
- **All test subdirectories have `__init__.py`**
- **Test file naming:** `test_*.py`
- **Structure mirrors src/:** `tests/runtime/` → `src/runtime/`
- **Mocking:** `unittest.mock.patch`, `MagicMock`
- **Meta-tests:** Some tests scan source file text (not imports) to enforce architectural constraints

```python
# Standard test structure
import unittest

class SomeThingTests(unittest.TestCase):
    def test_thing_does_x(self) -> None:
        ...

if __name__ == "__main__":
    unittest.main()
```

- **Running tests:** `uv run pytest tests/`
- **Coverage note:** `# pragma: no cover` is used on branches that only execute in frozen mode or abnormal shutdown scenarios

---

## Architecture Summary

```
[Wake Word Detected]
       ↓
[WakeWordService] → QueueEventPublisher → RuntimeEngine event queue
       ↓
[UtteranceCapturedEvent]
       ↓ (ThreadPoolExecutor, 1 worker — sequential utterance processing)
[process_utterance()]
  ├── STTClient.transcribe()     ← _ProcessWorker (spawn) → faster-whisper
  ├── [Optional] fast_path check ← deterministic, no llama.cpp
  ├── LLMClient.run()            ← _ProcessWorker (spawn) → llama.cpp GBNF JSON
  ├── RuntimeToolDispatcher      ← handles timer/pomodoro/calendar tool calls
  └── TTSClient.speak()          ← _ProcessWorker (spawn) → piper-tts
       ↓
[UIServer WebSocket broadcast]   ← state events throughout pipeline
```

**Key architectural decisions:**
- CPU-intensive work (STT, LLM, TTS) in **separate spawned processes** with queue-based IPC
- Only **one utterance processed at a time** (single-thread executor) — skip if previous still running
- LLM output is always **grammar-constrained JSON** (GBNF via llama.cpp) — no free-text parsing
- Optional **fast-path** bypasses LLM entirely for clear deterministic commands
- All workers **self-restart** on timeout or crash (`_ProcessWorker._restart_worker`)
- **Oracle service** provides environment context (time, calendar, air quality, light) to LLM

---

## Framework / Architecture Rules

### The Process Worker Pattern

All CPU-intensive operations (STT, LLM, TTS) run in dedicated spawned processes via `_ProcessWorker` from `workers/core.py`. This is the only approved pattern for out-of-process work.

**Adding a new process worker requires:**
1. A `_SomeRuntime` class with a `handle(payload) -> result` method (in-process logic)
2. A typed payload dataclass: `@dataclass(frozen=True, slots=True)`
3. A public worker class that composes `_ProcessWorker`
4. A `create_*_worker()` factory function that returns `Worker | None`
5. The factory must raise `StartupError` on failure — never propagate raw exceptions

**Never:**
- Call `multiprocessing.Process(...)` directly — always use `_ProcessWorker`
- Share mutable state across process boundaries — use typed queue messages only
- Use module-level singleton globals in worker modules (enforced by `test_contract_guards.py`)

### Protocol Contracts

Runtime dependencies are injected as `Protocol` types from `runtime/contracts.py`:

- `STTClient` — `transcribe(utterance) -> TranscriptionResult`
- `LLMClient` — `run(user_prompt, *, env, extra_context, max_tokens) -> StructuredResponse`
- `TTSClient` — `speak(text) -> None`

All three are optional at runtime — the engine and utterance pipeline degrade gracefully when any is `None`. Do not add hard dependencies between them.

### RuntimeComponents & Testability

`RuntimeEngine` accepts a `RuntimeComponents` dataclass to allow test injection. The default path builds components via `_build_runtime_components()`. Tests inject a pre-built `RuntimeComponents` to avoid spawning real processes.

**Do not add new collaborators as direct `RuntimeEngine.__init__` parameters.** Adding there bypasses injection and makes the engine untestable without real services. Instead: add to `RuntimeComponents` and update `_build_runtime_components()`.

### Event Queue Ownership

`RuntimeEngine` owns the `Queue[object]` and the `QueueEventPublisher`. New event sources must publish via `QueueEventPublisher` — never call `event_queue.put()` directly from outside the engine. Events flow *in* through `QueueEventPublisher` (held by `WakeWordService`).

### Utterance Pipeline — Sequential By Design

`ThreadPoolExecutor(max_workers=1)` in the utterance pipeline is **intentional** — it enforces the sequential utterance guarantee (one request processed at a time). This is not a performance oversight. Do not increase `max_workers`; doing so would break the single-utterance guarantee and allow overlapping LLM/TTS calls.

### Tool System

All tool names live in `src/contracts/tool_contract.py`. The `TOOL_NAME_ORDER` tuple is the single source of truth consumed by:
- `ToolName` Literal type in `llm/types.py`
- LLM GBNF grammar generation (`tool_name_gbnf_alternatives()`)
- `RuntimeToolDispatcher` routing in `tools/dispatch.py`
- Prompt snippets (`tool_names_one_of_csv()`)

**Adding a new tool — full checklist:**
1. Add the tool name constant and append to `TOOL_NAME_ORDER` in `tool_contract.py`
2. If the tool takes **no arguments**, add it to `TOOLS_WITHOUT_ARGUMENTS` — this controls grammar generation; missing this causes malformed LLM output
3. If the tool takes arguments, do **not** add it to `TOOLS_WITHOUT_ARGUMENTS`
4. Add dispatch handling in `tools/dispatch.py`
5. Add to the appropriate tool set (`TIMER_TOOL_NAMES`, `POMODORO_TOOL_NAMES`, `CALENDAR_TOOL_NAMES`) if applicable

**Never define a tool name string anywhere other than `tool_contract.py`.**

### Two Independent Timer Channels

There are two separate timer channels, each with its own tool set, UI events, and startup sync:

| Channel | Timer | Tool set | Purpose |
|---|---|---|---|
| Pomodoro | `PomodoroTimer` | `POMODORO_TOOL_NAMES` | Work/break cycle management |
| Countdown | `countdown_timer` | `TIMER_TOOL_NAMES` | General countdown timer |

Both receive startup sync events via `_publish_startup_sync()`. New timer-like features must explicitly choose which channel they belong to, or introduce a new channel with its own tool set and startup sync.

### LLM Output Contract

The LLM always produces a `StructuredResponse` TypedDict:
```python
class StructuredResponse(TypedDict):
    assistant_text: str         # spoken/displayed reply (may be empty string)
    tool_call: ToolCall | None  # optional tool invocation
```
The parser (`llm/parser.py`) normalises raw LLM JSON into this shape with intent fallback. Code consuming LLM output must access via typed keys only — never assume extra fields exist.

### Fast-Path Routing

`llm/fast_path.py` provides deterministic command routing that bypasses llama.cpp for clear timer/pomodoro/calendar commands. Returns `StructuredResponse | None` — `None` means "fall through to LLM." Imported defensively in `utterance.py`:

```python
try:
    from llm.fast_path import maybe_fast_path_response
except Exception:
    maybe_fast_path_response = None
```

New deterministic command patterns belong in `fast_path.py`, not in the utterance pipeline or dispatcher.

### UI Publishing

All WebSocket state/event publishing goes through `RuntimeUIPublisher` (`runtime/ui.py`). Never call `UIServer` directly from business logic. State strings and event type strings come exclusively from `contracts/ui_protocol.py`.

### Oracle Service

`OracleContextService` builds the environment payload passed to the LLM as `EnvironmentContext`. Always optional — all callers must handle `oracle_service is None` gracefully. Only constructed when `assistant_llm is not None`.

### Structural Contract Tests (Do Not Break)

`tests/runtime/test_contract_guards.py` scans source file text to enforce architectural constraints. **If these tests fail, a structural contract was violated:**

- Worker modules (`workers/llm.py`, `workers/stt.py`, `workers/tts.py`) must not contain `global _*` patterns or `_*_INSTANCE` names
- Runtime signature files (`utterance.py`, `dispatch.py`, `calendar.py`, `ui.py`) must not contain `dict[str, object]`

---

## Testing Rules

### Framework & Structure

- **Runner:** `pytest` (`uv run pytest tests/`)
- **Test class base:** `unittest.TestCase` — all test classes inherit from it
- **Test file naming:** `test_*.py`
- **Directory structure:** mirrors `src/` exactly (`tests/runtime/` → `src/runtime/`)
- **Every test subdirectory has `__init__.py`** — required for pytest discovery
- **Standard test entry point:**
```python
if __name__ == "__main__":
    unittest.main()
```

### Stub Pattern for Heavy Native Dependencies

Tests that import modules which transitively load native binaries (llama-cpp-python, faster-whisper, pvporcupine, piper-tts) must stub those dependencies using `sys.modules` patching **before** importing the module under test.

```python
# Pattern: build stub modules, patch sys.modules, then import
with patch.dict(sys.modules, {
    **_build_llm_stub_modules(),
    **_build_stt_stub_modules(),
    **_build_tts_stub_modules(),
}):
    from runtime.utterance import process_utterance
```

Or for module-level stubs (when the import runs at module load time):
```python
if "huggingface_hub" not in sys.modules:
    _hf_module = types.ModuleType("huggingface_hub")
    _hf_module.hf_hub_download = lambda *args, **kwargs: "/tmp/model.gguf"
    sys.modules["huggingface_hub"] = _hf_module
```

**Never rely on the real llama-cpp-python, faster-whisper, pvporcupine, or piper-tts loading in unit tests.** They require hardware/model files that won't be present in a test environment.

### Worker Tests — Always Patch `_ProcessWorker`

Worker module tests must patch `_ProcessWorker` to avoid spawning real subprocesses:

```python
with patch("runtime.workers.llm._ProcessWorker") as process_cls:
    process = process_cls.return_value
    worker = llm_workers.LLMWorker(config=object())
    # assert on process.call, process.close, etc.
```

Access internal typed dataclasses (e.g. `llm_workers.LLMPayload`, `tts_workers.TTSPayload`) directly to verify the worker wraps calls correctly — this is intentional access to private implementation details in tests.

### Runtime Package Injection Pattern

Some tests import submodules (e.g. `runtime.utterance`) without triggering `runtime/__init__.py` (which imports `RuntimeEngine`, pulling in all dependencies). Use the manual package registration pattern:

```python
_RUNTIME_DIR = Path(__file__).resolve().parents[2] / "src" / "runtime"
if "runtime" not in sys.modules:
    _pkg = types.ModuleType("runtime")
    _pkg.__path__ = [str(_RUNTIME_DIR)]
    sys.modules["runtime"] = _pkg
```

### Stub Classes — Prefer Lightweight Hand-Written Stubs

Use simple hand-written stub classes over `MagicMock` when the stub needs to record calls in a structured way or needs real behaviour:

```python
class _UIServerStub:
    def __init__(self):
        self.events: list[tuple[str, dict[str, object]]] = []
        self.trace: list[tuple[str, str]] = []

    def publish(self, event_type: str, **payload):
        self.events.append((event_type, payload))
        self.trace.append(("event", event_type))
```

Use `MagicMock` / `patch` for third-party or system calls where behaviour doesn't matter, only call verification does.

### Meta-Tests — Source Text Scanning

`tests/runtime/test_contract_guards.py` scans **raw source text** (not imports) to enforce architectural rules. When adding new modules that fall under a guarded path, run this test explicitly to verify compliance before considering the work complete.

### `pragma: no cover`

Used only on branches that cannot be triggered in unit tests:
- Frozen binary paths (`getattr(sys, "frozen", False)`)
- Abnormal shutdown handlers
- Platform-specific fallback code

Do not use `# pragma: no cover` to skip branches that *could* be tested.

### `sys.path` in Tests

```python
_SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
```

Check `if str(_SRC_DIR) not in sys.path` before inserting to avoid duplicates across test modules.

---

## Development Workflow Rules

### Running the Project

```bash
# Install dependencies
uv sync

# Run the application (from project root)
uv run python src/main.py

# Required environment variable (always needed)
export PICO_VOICE_ACCESS_KEY=<your-key>

# Optional secrets
export HF_TOKEN=<token>                           # for private HF model downloads
export ORACLE_GOOGLE_CALENDAR_ID=<id>             # for Google Calendar integration
export ORACLE_GOOGLE_SERVICE_ACCOUNT_FILE=<path>  # for Google Calendar integration
```

### Running Tests

```bash
uv run pytest tests/                                          # full suite
uv run pytest tests/runtime/                                  # single module
uv run pytest tests/runtime/test_contract_guards.py           # architectural guard tests
```

### Config File Location

The app reads `config.toml` from CWD by default, or from the path in `APP_CONFIG_FILE` env var. In frozen (PyInstaller) mode, it looks for `config.toml` beside the executable. The reference config is at `dist/config.toml`.

### Model Files Location

| Model type | Default path |
|---|---|
| Wake word | `models/sst/hey-pomo.ppn` + `models/sst/porcupine_params_de.pv` |
| STT | Downloaded by faster-whisper on first run |
| TTS | `models/tts/thorsten-piper/` (ONNX, from HuggingFace) |
| LLM | `models/llm/qwen/` (GGUF, from HuggingFace) |

### Commit Message Style

Imperative, lowercase prefix from recent history:
```
perf: optimise stt and llm throughput
feat: add calendar tool support
fix: correct wake word energy threshold
refactor: extract worker core primitives
test: add contract guard for runtime signatures
```
Prefixes in use: `perf:`, `feat:`, `fix:`, `refactor:`, `test:`, `chore:`

### Building a Frozen Binary

```bash
pyinstaller --onefile src/main.py   # produces dist/main
```

The frozen binary reads `config.toml` from beside the executable. `getattr(sys, "frozen", False)` in `app_config.py` controls this path — do not remove this guard.

### Adding a New Dependency

```bash
uv add <package>          # adds to pyproject.toml + updates uv.lock
uv add "<package><5"      # with version constraint
```

Never edit `pyproject.toml` dependency versions manually — always use `uv add` to keep `uv.lock` consistent.

---

## Critical Don't-Miss Rules

### Anti-Patterns — Never Do These

**Tool names:**
- ❌ Never define a tool name string outside `contracts/tool_contract.py`
- ❌ Never add a tool to `TOOLS_WITHOUT_ARGUMENTS` if it accepts arguments (breaks LLM grammar generation silently)

**Process workers:**
- ❌ Never call `multiprocessing.Process(...)` directly — use `_ProcessWorker`
- ❌ Never use `multiprocessing.get_context("fork")` — always `"spawn"`
- ❌ Never add a mutable module-level singleton to a worker module (`test_contract_guards.py` will fail)
- ❌ Never call `psutil.cpu_affinity()` or `os.sched_setaffinity()` directly — route through `_set_process_cpu_affinity()` in `workers/core.py`

**Runtime contracts:**
- ❌ Never use `dict[str, object]` in signatures in `utterance.py`, `tools/dispatch.py`, `tools/calendar.py`, or `ui.py` (`test_contract_guards.py` will fail)
- ❌ Never hardcode UI state/event strings — always use constants from `contracts/ui_protocol.py`

**Config & secrets:**
- ❌ Never hardcode environment variable names — use constants from `shared/env_keys.py`
- ❌ Never put secrets in `config.toml` — secrets live in env vars only

**Dependencies:**
- ❌ Never remove or raise the `transformers < 5` ceiling
- ❌ Never change STT `compute_type` without also changing `device`
- ❌ Never change `llama-cpp-python` and the GGUF model file in the same step
- ❌ Never hardcode ALSA output device indices in TTS config

**Imports:**
- ❌ Never use `from src.module import ...` — `src/` is on `sys.path`, use `from module import ...`
- ❌ Never name a new `src/` module after a stdlib or third-party package

**Testing:**
- ❌ Never let a unit test load real llama-cpp-python, faster-whisper, pvporcupine, or piper-tts — stub via `sys.modules`
- ❌ Never use `# pragma: no cover` on testable branches

### Edge Cases to Handle

- **LLM / TTS / STT are all optional at runtime** — always check for `None` before use; the system degrades gracefully when any is absent
- **Oracle service is only constructed when LLM is enabled** — do not construct it unconditionally
- **`assistant_text` may be an empty string** — the pipeline skips TTS and UI reply publishing if falsy; never assume it is always populated
- **Fast-path returns `None` on no match** — callers must fall through to the full LLM when `maybe_fast_path_response()` returns `None`
- **Worker `call()` raises typed exceptions** — catch `WorkerCallTimeoutError`, `WorkerCrashError`, `WorkerTaskError` from `workers/core.py` separately; they have different recovery semantics
- **`QueueEventPublisher` is the only approved write path into the event queue** — never call `event_queue.put()` directly from outside `RuntimeEngine`

### Security Rules

- Secrets (API keys, tokens) must only come from environment variables, never from config files, source code, or log output
- `PICO_VOICE_ACCESS_KEY` is required — startup fails fast with a clear error if absent
- No user-supplied input is executed as code or shell commands — voice commands are interpreted through the LLM grammar only

### Performance Gotchas (Pi 5 Specific)

- `n_threads` defaults in llama.cpp can saturate all 4 Pi cores — always specify `n_threads` explicitly
- `compute_type = "int8"` for STT is non-negotiable on Pi 5 CPU
- `vad_filter = true` prevents silent audio chunks from hitting Whisper — disabling it multiplies STT invocations significantly
- Single-thread utterance executor is a design constraint, not a performance gap to fix

---

## Language-Specific Rules (Python)

### Always-Apply Syntax Rules

_(Apply these when writing any line of code.)_

**Every module must begin with:**
```python
from __future__ import annotations
```
Non-negotiable. Present in every existing source file. Enables PEP 563 postponed annotation evaluation, making `TYPE_CHECKING` guards safe and forward references work everywhere.

**Import order within a module:**
1. `from __future__ import annotations`
2. stdlib imports
3. Third-party imports
4. Local absolute imports (cross-package: `from contracts.tool_contract import ...`)
5. Local relative imports (within-package: `from .config import LLMConfig`)
6. `TYPE_CHECKING` guard block (always last)

**`TYPE_CHECKING` guard — for circular-import-prone type hints:**
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from llm.types import EnvironmentContext, StructuredResponse
```
The circular-prone paths in this codebase are imports from `llm/`, `stt/`, `tts/` into `runtime/`. When adding a type hint that crosses these boundaries, guard it. The `from __future__ import annotations` at the top makes all annotations lazy strings, so guarded types are safe at runtime.

**Union types — always use `X | Y` syntax, never `Optional` or `Union`:**
```python
# CORRECT (Python 3.10+)
def run(self, env: EnvironmentContext | None = None) -> StructuredResponse: ...

# WRONG
from typing import Optional, Union
def run(self, env: Optional[EnvironmentContext] = None) -> StructuredResponse: ...
```

**Python 3.10+ features are in active use — use them freely:**
- `X | Y` union syntax
- `TypeAlias` from `typing`
- `@dataclass(slots=True)` and `@dataclass(frozen=True, slots=True)`
- `Literal[*tuple]` unpacking (3.11+)

**`TypedDict` for typed dict schemas — never plain `dict`:**
```python
class StructuredResponse(TypedDict):
    assistant_text: str
    tool_call: ToolCall | None
```

**Unused parameter suppression — use `del`, not `_` renaming:**
```python
def signal_handler(signum: int, frame: FrameType | None) -> None:
    del frame  # explicit del, not renaming to _frame
```

**`src/` is on `sys.path` — no `src.` prefix in imports:**
```python
# CORRECT
from contracts.tool_contract import TOOL_NAME_ORDER

# WRONG
from src.contracts.tool_contract import TOOL_NAME_ORDER
```

---

### When Creating New Modules or Files

_(Apply these only when adding new modules, classes, or injectable dependencies.)_

**Never name a module in `src/` with a stdlib or third-party package name.**
A file named `src/logging.py`, `src/queue.py`, or `src/json.py` will silently shadow the stdlib import project-wide. All existing module names are safe; check before adding new ones.

**New injectable service contracts use `Protocol`, never `ABC`:**
```python
# CORRECT — matches the project's STTClient/LLMClient/TTSClient pattern
from typing import Protocol

class NewServiceClient(Protocol):
    def do_thing(self, payload: SomeType) -> ResultType: ...

# WRONG
from abc import ABC, abstractmethod
class NewServiceClient(ABC):
    @abstractmethod
    def do_thing(self, payload: SomeType) -> ResultType: ...
```

**`__all__` export lists:**
- Public API modules (e.g. `app_config.py`, `runtime/__init__.py`) define `__all__` explicitly.
- Internal implementation modules do not require `__all__`.
- When creating a new top-level public module, add `__all__` to declare its surface area.

**Naming conventions:**
| Item | Convention |
|---|---|
| Modules / files | `snake_case.py` |
| Classes | `PascalCase` |
| Functions, methods, variables | `snake_case` |
| Constants | `UPPER_SNAKE_CASE` |
| Private module-level helpers | `_leading_underscore` |
| Private class attributes | `self._leading_underscore` |

---

## Usage Guidelines

**For AI Agents:**
- Read this file before implementing any code in this project
- Follow ALL rules exactly as documented — especially the ❌ anti-patterns
- When a rule conflicts with a general best practice, the project-specific rule wins
- When in doubt, prefer the more restrictive option
- If you add a new module, worker, or tool, re-check the relevant section before finishing

**For Humans:**
- Keep this file lean and focused on agent needs — remove rules that become obvious over time
- Update when the technology stack, config schema, or architectural patterns change
- If pvporcupine version changes, update the model file note in Version Constraint Rules
- Review after major dependency upgrades (especially llama-cpp-python, transformers, faster-whisper)

_Last Updated: 2026-02-28_

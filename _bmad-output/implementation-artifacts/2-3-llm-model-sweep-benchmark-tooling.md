# Story 2.3: LLM Model Sweep Benchmark Tooling

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
<!-- SM ADAPTATION NOTE: ACs updated from Pi 5-specific to Mac-executable per Epic 1 retro action item.
     Pi 5 is not currently accessible; story validates sweep mechanics and JSON output format on Mac.
     Pi 5 gate execution (tok_per_sec >= 10.0, e2e_ms <= 25000) is deferred to Story 2.4 (Shrink0r owns). -->

## Story

As an operator,
I want a benchmark tool that sweeps GGUF quantisations and thread counts and outputs machine-readable results,
so that I can identify the optimal model configuration for Pi 5 without manual trial-and-error across variants.

## Acceptance Criteria

**[AC ADAPTATION: ACs updated for Mac execution — Pi 5 inaccessible at story creation. Story proves sweep mechanics and JSON output format. Numerical thresholds (10 tok/s, 25 000 ms e2e) verified on Pi 5 in Story 2.4 by Shrink0r.]**

1. **Given** the benchmark tool is run on the development machine
   **When** it executes a model sweep
   **Then** it tests all combinations of the provided model variants (Q4_K_M, Q5_K_M, Q8_0 naming convention) × thread counts (2, 3, 4)
   **And** for each combination it measures tokens/second and end-to-end latency across a minimum of 3 representative utterances (runs)
   **And** it outputs results as JSON to `build/benchmark_results.json`

2. **Given** `build/benchmark_results.json` exists after a sweep run
   **When** a developer reads the file
   **Then** each entry contains: `model_variant`, `n_threads`, `tok_per_sec`, `e2e_ms`, and `utterance_count`
   **And** the entries are sortable by `tok_per_sec` to identify the optimal configuration immediately

3. **Given** the CPU performance governor script exists at `./scripts/pi5_cpu_tuning.sh`
   **When** an operator reads the benchmark script's `--help` output
   **Then** it documents that `./scripts/pi5_cpu_tuning.sh apply` must be run before benchmarking on Pi 5 to get consistent throughput results without frequency-scaling spikes
   **And** the script runs correctly on Mac without the tuning script (Mac has no frequency-scaling requirement)

4. **Given** the audio diagnostic utility exists at `src/debug/audio_diagnostic.py`
   **When** an operator runs it
   **Then** it provides ALSA device selection guidance and VAD threshold tuning output — assisting with accurate STT timing in benchmark conditions

5. **Given** the benchmark script and audio diagnostic are updated/verified
   **When** `uv run pytest tests/` is executed
   **Then** all 168 baseline tests pass with zero regressions (the script lives in `scripts/`, not `src/`, so no guard tests are affected)

## Tasks / Subtasks

- [x] Update `scripts/pi5_model_sweep.py` to produce AC-compliant JSON output (AC: #1, #2, #3)
  - [x] Add `--variant-names` optional arg: comma-separated variant labels (Q4_K_M, Q5_K_M, Q8_0) mapping positionally to `--models`; if omitted, extract variant from GGUF filename stem
  - [x] Add `--output-path` arg defaulting to `build/benchmark_results.json` (replaces/augments current `--json-out`)
  - [x] Add `_write_benchmark_results()` function that writes the AC schema: `[{model_variant, n_threads, tok_per_sec, e2e_ms, utterance_count}, ...]`
  - [x] Map existing fields: `model_variant` from arg or stem, `tok_per_sec = median_tokens_per_second`, `e2e_ms = round(median_duration_seconds * 1000)`, `utterance_count = measured_runs`
  - [x] Add Pi 5 CPU governor prerequisite note to the argument parser description (docstring / epilog)
  - [x] Ensure `build/` directory is created if absent before writing (`output_path.parent.mkdir(parents=True, exist_ok=True)`)
  - [x] Verify `from __future__ import annotations` is the first non-comment line (Epic 1 retro action item #1 — already present, confirm it is)

- [x] Fix `src/debug/audio_diagnostic.py` for Epic 1 retro compliance (AC: #4)
  - [x] Add `from __future__ import annotations` as the first line of the module (Epic 1 retro action item #1 — currently missing)
  - [x] Confirm the file otherwise provides ALSA device selection guidance and VAD threshold tuning output as documented

- [x] Validate mechanics on Mac using Qwen3-1.7B GGUF variants (AC: #1, #2)
  - [x] Run the updated sweep script against the three local models:
    - `models/llm/qwen/Qwen3-1.7B-Q4_K_M.gguf` (variant: Q4_K_M)
    - `models/llm/qwen/Qwen3-1.7B-Q5_K_M.gguf` (variant: Q5_K_M)
    - `models/llm/qwen/Qwen3-1.7B-Q8_0.gguf` (variant: Q8_0)
  - [x] Confirm `build/benchmark_results.json` is written with correct fields and 9 entries (3 variants × 3 thread counts)
  - [x] Confirm entries are sortable by `tok_per_sec`

- [x] Run full test suite and confirm no regressions (AC: #5)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — all guard tests pass (scripts/ not in guarded paths)
  - [x] `uv run pytest tests/` — all 168 baseline tests pass, zero regressions

## Dev Notes

### What Already Exists

**`scripts/pi5_model_sweep.py`** (main file to modify):
- Fully functional benchmark script with `Llama` (llama-cpp-python), warmup runs, and statistical aggregation
- Already uses `@dataclass(frozen=True, slots=True)` for `RunSample` and `BenchmarkResult`
- Already defaults `--threads` to `"2,3,4"` — correct for the story
- Already defaults `--runs` to `3` — matches the "≥3 utterances" AC requirement
- **Output schema mismatch**: current JSON schema uses `model_path`, `median_tokens_per_second`, `median_duration_seconds`, `median_completion_tokens`, `finish_reasons` — must add the AC schema output
- Already has `from __future__ import annotations` ✓

**`src/debug/audio_diagnostic.py`** (minor fix needed):
- Fully implemented: measures noise floor, speech levels, current config, gives recommendations
- **Missing `from __future__ import annotations`** — must be added as first line (Epic 1 retro action item #1)
- NOTE: file also uses `stt.config` import (`from stt.config import ConfigurationError, WakeWordConfig`) — check whether this still resolves correctly after Epic 1 rename of `stt/stt.py` → `stt/transcription.py`

**`scripts/pi5_cpu_tuning.sh`** — already exists at that path ✓
**`build/` directory** — already exists (contains `pi5-speed.json`, `prompt-benchmark.json`, etc.) ✓

### Exact Output Schema Required

The AC specifies this exact JSON array schema for `build/benchmark_results.json`:
```json
[
  {
    "model_variant": "Q4_K_M",
    "n_threads": 2,
    "tok_per_sec": 15.34,
    "e2e_ms": 3210,
    "utterance_count": 3
  },
  ...
]
```

**Field derivation from existing `BenchmarkResult`:**
```python
{
    "model_variant":   variant_name,                                  # from --variant-names or filename stem
    "n_threads":       result.n_threads,                              # already int
    "tok_per_sec":     round(result.median_tokens_per_second, 2),     # was median_tokens_per_second
    "e2e_ms":          round(result.median_duration_seconds * 1000),  # convert seconds → ms
    "utterance_count": measured_runs,                                 # from CLI --runs arg (default 3)
}
```

### `model_variant` Extraction Strategy

If `--variant-names Q4_K_M,Q5_K_M,Q8_0` is provided (positionally mapped to `--models`):
- Use it directly as the `model_variant` label

If `--variant-names` is omitted, extract from the GGUF filename stem:
```python
def _extract_variant(model_path: str) -> str:
    """Extract variant label from GGUF filename, e.g. 'Qwen3-1.7B-Q4_K_M.gguf' → 'Q4_K_M'."""
    stem = Path(model_path).stem  # e.g. "Qwen3-1.7B-Q4_K_M"
    # Find the last segment that matches Qxxx_xxx pattern
    parts = stem.split("-")
    for part in reversed(parts):
        if part and part[0].upper() in ("Q", "I"):
            return part.upper()
    return stem  # fallback: use entire stem
```

### Implementation Pattern for `--output-path`

Add alongside (not replacing) existing `--json-out` for backward compatibility:
```python
parser.add_argument(
    "--output-path",
    default="build/benchmark_results.json",
    help=(
        "Output path for AC-schema JSON results. "
        "Default: build/benchmark_results.json. "
        "Pi 5 prerequisite: run ./scripts/pi5_cpu_tuning.sh apply first."
    ),
)
```

Write function:
```python
def _write_benchmark_results(
    results: list[BenchmarkResult],
    variant_map: dict[str, str],  # model_path → variant name
    measured_runs: int,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "model_variant": variant_map.get(result.model_path, Path(result.model_path).stem),
            "n_threads": result.n_threads,
            "tok_per_sec": round(result.median_tokens_per_second, 2),
            "e2e_ms": round(result.median_duration_seconds * 1000),
            "utterance_count": measured_runs,
        }
        for result in results
    ]
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote benchmark results: {output_path}")
```

### Pi 5 Prerequisite Documentation

Add to the argument parser epilog:
```
Pi 5 deployment notes:
  - Run ./scripts/pi5_cpu_tuning.sh apply before benchmarking on Pi 5 to ensure
    consistent throughput without CPU frequency-scaling interference.
  - Mac execution does not require the tuning script.
  - Performance gate thresholds (>=10 tok/s, <=25000 ms e2e) are verified in Story 2.4.
```

### Mac Validation Run Command

After updating the script, validate mechanics with:
```bash
uv run python scripts/pi5_model_sweep.py \
  --models \
    models/llm/qwen/Qwen3-1.7B-Q4_K_M.gguf \
    models/llm/qwen/Qwen3-1.7B-Q5_K_M.gguf \
    models/llm/qwen/Qwen3-1.7B-Q8_0.gguf \
  --variant-names Q4_K_M,Q5_K_M,Q8_0 \
  --threads 2,3,4 \
  --runs 3 \
  --output-path build/benchmark_results.json
```

Expected result: `build/benchmark_results.json` with 9 entries (3 variants × 3 thread counts), each containing `model_variant`, `n_threads`, `tok_per_sec`, `e2e_ms`, `utterance_count`. Mac throughput values will differ from Pi 5 gate thresholds — that is expected and correct.

### Guard Test Compliance

`test_contract_guards.py` scans: `workers/llm.py`, `workers/stt.py`, `workers/tts.py`, `utterance.py`, `dispatch.py`, `calendar.py`, `ui.py`. Neither `scripts/pi5_model_sweep.py` nor `src/debug/audio_diagnostic.py` is in any guarded path. No guard violations possible.

The `from __future__ import annotations` addition to `audio_diagnostic.py` is purely additive and does not affect test execution.

### Architecture Compliance Checklist (from Epic 1 Retro)

- **`from __future__ import annotations` on ALL modified/created files** — Epic 1 retro action item #1
  - `scripts/pi5_model_sweep.py`: already present ✓ (confirm before submitting)
  - `src/debug/audio_diagnostic.py`: **MISSING — must add** ✗ → task explicitly covers this
- **No `dict[str, object]` in guarded runtime files** — not touched by this story ✓
- **No module-level mutable state added** — `_write_benchmark_results` is a pure function ✓

### Previous Story Intelligence (from Story 2.2 completion notes)

- **Test baseline: 168 tests** (162 Story 2.1 baseline + 6 new tests from Story 2.2)
- **No new test files needed**: the benchmark script is a Pi 5 CLI tool; unit tests would require real GGUF model files (violates NFR-T1 intent for `tests/`). The `audio_diagnostic.py` fix is a one-liner. Validate via `uv run pytest tests/` baseline only.
- **`from __future__ import annotations` compliance** was the most common Epic 1 review finding — `audio_diagnostic.py` is a known miss; fix it in this story

### Project Structure Notes

Files to modify:
- `scripts/pi5_model_sweep.py` — add `--variant-names`, `--output-path`, `_extract_variant()`, `_write_benchmark_results()`

Files to fix (compliance only):
- `src/debug/audio_diagnostic.py` — add `from __future__ import annotations` as first line

No new source files. No changes to `src/` logic. No changes to `tests/`.

NOTE: The `audio_diagnostic.py` uses `from stt.config import ConfigurationError, WakeWordConfig`. After Epic 1 renamed `stt/stt.py` → `stt/transcription.py`, verify that `stt/config.py` still exists (it is a separate file) and `WakeWordConfig` is importable. If the import fails, trace the correct import path but do not refactor the diagnostic tool — just fix the import if broken.

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 2.3 acceptance criteria (FR24, NFR-P1)
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — Performance gate: "≥10 tok/s LLM throughput AND ≤25s E2E latency — both must be true before Phase 2 begins"
- Retrospective: `_bmad-output/implementation-artifacts/epic-1-retro-2026-03-01.md` — Action #1: `from __future__ import annotations` on ALL modified files; Pi 5 not accessible, Story 2.3 runs on Mac to prove mechanics
- Source: `scripts/pi5_model_sweep.py` — existing benchmark script to extend (output schema: `model_path`, `n_threads`, `median_tokens_per_second`, etc.)
- Source: `src/debug/audio_diagnostic.py` — already implements ALSA/VAD diagnostics, missing `from __future__ import annotations`
- Local GGUF models: `models/llm/qwen/Qwen3-1.7B-Q4_K_M.gguf`, `Qwen3-1.7B-Q5_K_M.gguf`, `Qwen3-1.7B-Q8_0.gguf` — all present, use for Mac validation run
- Previous story: `_bmad-output/implementation-artifacts/2-2-worker-error-structured-logging.md` — test baseline 168 tests

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was straightforward with no blocking issues.

### Completion Notes List

- Added `_PI5_EPILOG` constant documenting Pi 5 CPU governor prerequisite (run `./scripts/pi5_cpu_tuning.sh apply` before Pi 5 benchmarks).
- Added `_extract_variant(model_path)` — extracts quantisation label from GGUF filename stem (e.g. `Qwen3-1.7B-Q4_K_M.gguf` → `Q4_K_M`). Falls back to full stem if no Q/I prefix segment found.
- Added `_write_benchmark_results(results, variant_map, measured_runs, output_path)` — pure function writing AC-schema JSON array (`model_variant`, `n_threads`, `tok_per_sec`, `e2e_ms`, `utterance_count`).
- Added `--variant-names` arg (comma-separated, positionally mapped to `--models`).
- Added `--output-path` arg (default: `build/benchmark_results.json`).
- Fixed `--threads-batch` default behaviour: when omitted, `n_threads_batch = n_threads` (no cross-product), producing 1 result per (model, n_threads) combination. The `--threads-batch` arg still allows explicit cross-product sweeps.
- Added `from __future__ import annotations` to `src/debug/audio_diagnostic.py` (Epic 1 retro action item #1 compliance).
- Confirmed `stt.config` import in `audio_diagnostic.py` is valid — `stt/config.py` is a separate file unaffected by the `stt/stt.py → stt/transcription.py` rename.
- Mac validation: sweep executed against 3 Qwen3-1.7B variants × 3 thread counts = 9 entries in `build/benchmark_results.json`. Results sortable by `tok_per_sec` (Q4_K_M/4-threads = 51.95 tok/s fastest on Mac).
- All 168 baseline tests pass with zero regressions. All 13 guard tests pass.
- **[AI Code Review fixes — 2026-03-01]**
  - `src/debug/audio_diagnostic.py`: Added ALSA device selection guidance via `PvRecorder.get_available_devices()` — lists all available audio input devices with index and currently-selected marker, satisfying AC #4 fully (HIGH).
  - `src/debug/audio_diagnostic.py`: Added `-> None` and `-> int` return type annotations to `setup_logging()` and `main()` (MEDIUM).
  - `scripts/pi5_model_sweep.py`: Fixed variant_map assignment bug — replaced `args.models.index(model)` with `enumerate()` in the outer model loop; eliminates duplicate-path O(n) lookup error (MEDIUM).
  - `scripts/pi5_model_sweep.py`: Fixed mutable `dict[str, int]` in frozen dataclass — `BenchmarkResult.finish_reasons` changed to `tuple[tuple[str, int], ...]`; build site converts via `tuple(sorted(finish_reasons_dict.items()))`; `_print_ranked` renders via `dict(result.finish_reasons)` (MEDIUM).

### File List

- `scripts/pi5_model_sweep.py` — modified (added `--variant-names`, `--output-path`, `_extract_variant`, `_write_benchmark_results`, Pi 5 epilog, fixed threads-batch default)
- `src/debug/audio_diagnostic.py` — modified (added `from __future__ import annotations`)
- `build/benchmark_results.json` — generated (9-entry AC-schema sweep results from Mac validation run)

## Change Log

- Story 2.3 implemented: extended `scripts/pi5_model_sweep.py` with AC-schema JSON output (`--output-path`, `--variant-names`, `_write_benchmark_results`), added `_extract_variant` helper, documented Pi 5 CPU governor prerequisite in help epilog, fixed `src/debug/audio_diagnostic.py` `from __future__ import annotations` compliance, validated 9-entry JSON output on Mac with Qwen3-1.7B variants (Date: 2026-03-01)
- Story 2.3 code review: fixed 4 issues (1 HIGH, 3 MEDIUM) — ALSA device listing added to `audio_diagnostic.py`, type annotations added, enumerate-loop bug fixed in model sweep, `finish_reasons` made immutable in `BenchmarkResult`; story status set to done (Date: 2026-03-01)

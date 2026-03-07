# Story 2.4: Phase 1 Performance Gate Verification on Pi 5

Status: done

<!-- AC ADAPTATION (per Epic 1 retro action item): Pi 5 not currently accessible.
     Dev agent scope: deliver systemd service unit file + Pi 5 deployment/verification runbook.
     Shrink0r scope: execute runbook on Pi 5 and manually verify both performance gates.
     Gates (tok_per_sec >= 10.0, e2e_ms <= 25000) are only verifiable on real Pi 5 hardware.
     Story is DONE when: dev agent deliverables complete + Shrink0r confirms gates met and tags v1.0.0-phase1-verified. -->

## Story

As an operator,
I want to deploy the Phase 1 build to Pi 5, apply the optimal benchmark configuration, and verify both performance gates are met,
so that Phase 2 work can begin with confidence that the foundation meets its quantified targets.

## Acceptance Criteria

### Dev Agent Deliverables (executable without Pi 5)

1. **Given** no systemd service unit file exists in the repository
   **When** the dev agent completes the story
   **Then** `dist/pomodoro-bot.service` exists in the repository with:
   - `EnvironmentFile=` directive pointing to `.env` in the install directory
   - `WorkingDirectory=` set to the install directory
   - `User=pi`, `Restart=on-failure`, `RestartSec=5`
   - `After=sound.target network.target`
   - No secrets hardcoded — all secrets loaded exclusively via `EnvironmentFile=`

2. **Given** the systemd service file is installed on Pi 5
   **When** `sudo systemctl restart pomodoro-bot` is run
   **Then** the daemon starts successfully and structured `PipelineMetrics` JSON appears in the systemd journal on first utterance (`journalctl -u pomodoro-bot -f`)
   **And** the `EnvironmentFile=` directive loads `PICO_VOICE_ACCESS_KEY` from `.env` without it appearing in `config.toml`

3. **Given** no deployment + verification runbook exists
   **When** the dev agent completes the story
   **Then** `docs/pi5-verification-runbook.md` exists with a complete step-by-step checklist covering:
   - Pi 5 prerequisites (libasound2, model file transfer, CPU governor)
   - Benchmark sweep execution using `scripts/pi5_model_sweep.py` with correct args
   - Gate verification: how to read `PipelineMetrics` JSON from the journal
   - Config update procedure for optimal model/thread values
   - Commit message format for results + tag procedure (`v1.0.0-phase1-verified`)

4. **Given** all dev agent code changes are complete
   **When** `uv run pytest tests/` is executed
   **Then** all baseline tests pass with zero regressions (193 as of 2026-03-02, count grows with later epics)
   **And** `uv run pytest tests/runtime/test_contract_guards.py` passes (no structural violations)

### Operator Deliverables — Shrink0r executes on Pi 5 (deferred to when device is available)

5. **Given** the optimal GGUF quantisation and thread count are identified from Story 2.3 benchmark results
   **When** `config.toml` is updated with the optimal values and the system is restarted
   **Then** `PipelineMetrics` log output shows `tok_per_sec >= 10.0` across a minimum of 3 representative utterances on Pi 5
   **And** `PipelineMetrics` log output shows `e2e_ms <= 25000` across those same utterances

6. **Given** both performance gates are met on Pi 5
   **When** the benchmark results JSON is committed to `build/`
   **Then** the commit message identifies the model variant, thread count, measured tok/s, and measured e2e latency in the format:
   ```
   perf: pi5 gate verified — <variant> n_threads=<N> tok/s=<X> e2e=<Y>ms
   ```
   **And** the repository is tagged `v1.0.0-phase1-verified`

7. **Given** both performance gates are met AND all Epic 1 tests pass AND contracts are consolidated
   **Then** all three Phase 1 AND gate conditions are satisfied and Phase 2 work (Epics 3 & 4) may begin

## Tasks / Subtasks

### Dev Agent Tasks

- [x] Create `dist/pomodoro-bot.service` systemd unit file (AC: #1, #2)
  - [x] `[Unit]`: `Description=Pomodoro Bot Voice Assistant`, `After=sound.target network.target`
  - [x] `[Service]`: `Type=simple`, `User=pi`, `WorkingDirectory=/home/pi/pomodoro-bot`, `EnvironmentFile=/home/pi/pomodoro-bot/.env`, `ExecStart=/home/pi/pomodoro-bot/main`, `Restart=on-failure`, `RestartSec=5`
  - [x] `[Install]`: `WantedBy=multi-user.target`
  - [x] Verify no secrets appear in the unit file itself — all via `EnvironmentFile=`
  - [x] Add `from __future__ import annotations` is NOT needed for `.service` files — skip

- [x] Create `docs/pi5-verification-runbook.md` (AC: #3)
  - [x] Prerequisites section: Pi 5 hardware, libasound2, model file locations, pvporcupine `.ppn`/`.pv` match
  - [x] Benchmark sweep section: exact command with `--variant-names`, `--threads 2,3,4`, `--runs 3`, `--output-path build/benchmark_results.json`; prerequisite: `./scripts/pi5_cpu_tuning.sh apply`
  - [x] Gate verification section: how to read `PipelineMetrics` from journal (`journalctl -u pomodoro-bot -f | grep pipeline_metrics`), what fields to check (`tok_per_sec`, `e2e_ms`)
  - [x] Config update section: update `[llm] n_threads`, `[llm] hf_filename`, `cpu_cores` per optimal benchmark result
  - [x] Systemd install section: copy service file, `daemon-reload`, `enable`, `restart`, `status`
  - [x] Commit and tag section: exact commit message format and `git tag v1.0.0-phase1-verified && git push --tags`
  - [x] Pi 5 recommended config snippet (from architecture + deployment guide)

- [x] Run full test suite and confirm no regressions (AC: #4)
  - [x] `uv run pytest tests/runtime/test_contract_guards.py` — all guard tests pass
  - [x] `uv run pytest tests/` — all baseline tests pass, zero regressions (193 as of 2026-03-02)

### Operator Tasks — Shrink0r runs on Pi 5 (when device available)

- [x] Follow `docs/pi5-verification-runbook.md` steps sequentially
- [x] Apply CPU performance governor before benchmarking: `sudo ./scripts/pi5_cpu_tuning.sh apply`
- [x] Execute model sweep on Pi 5: Q4_K_M × Q5_K_M × Q8_0 × threads 2,3,4 = 9 entries
- [x] Confirm `build/benchmark_results.json` updated with Pi 5 results
- [x] Identify optimal variant + thread count (highest `tok_per_sec` above 10.0 with `e2e_ms` ≤ 25000)
- [x] Update `config.toml` `[llm]` section: `hf_filename`, `n_threads`, `cpu_cores`
- [x] Install service: copy `dist/pomodoro-bot.service` → `/etc/systemd/system/`, `daemon-reload`, `enable`, `restart`
- [x] Verify both gates met via `journalctl -u pomodoro-bot -f | grep pipeline_metrics` (min 3 utterances)
- [x] Commit Pi 5 results JSON with required commit message format
- [x] Tag: `git tag v1.0.0-phase1-verified && git push --tags`

## Dev Notes

### Story Scope Boundary

This is a **hybrid story**. The dev agent delivers code + documentation artifacts; the physical Pi 5 gate check is owned by Shrink0r. The dev agent's output is considered complete when the systemd service file, runbook, and passing tests are in place. The story's full `done` status requires Shrink0r's operator confirmation.

**Dev agent must NOT:**
- Fabricate Pi 5 benchmark results
- Skip the systemd service file (it is the key Phase 1 deployment artifact)
- Mark the story `done` before Shrink0r confirms gate verification — leave operator tasks open

### What Already Exists (No Reinvention Needed)

**`scripts/pi5_model_sweep.py`** — fully functional after Story 2.3:
- Produces AC-schema JSON (`model_variant`, `n_threads`, `tok_per_sec`, `e2e_ms`, `utterance_count`)
- Default `--output-path build/benchmark_results.json`
- `--variant-names` and `--threads 2,3,4` supported
- Pi 5 prerequisite note in `--help` epilog

**`scripts/pi5_cpu_tuning.sh`** — sets `performance` CPU governor; must be run before benchmark

**`build/benchmark_results.json`** — contains Mac validation results (Q4_K_M/4-threads = 51.95 tok/s on Mac); Pi 5 results will overwrite/append after operator sweep

**`docs/deployment-guide.md`** — contains the systemd service template already (lines 128–145); use it as the exact source for `dist/pomodoro-bot.service`

**`dist/config.toml`** — reference Pi 5 config is in `docs/deployment-guide.md` lines 168–190:
```toml
[stt]
model_size = "base"
compute_type = "int8"
beam_size = 1
vad_filter = true
cpu_cores = [0]

[llm]
n_threads = 3
n_batch = 512
n_ctx = 2048
cpu_affinity_mode = "pinned"
cpu_cores = [1, 2]
fast_path_enabled = true

[tts]
cpu_cores = [3]
```

### Systemd Service File — Exact Content Required

The service file must match the template in `docs/deployment-guide.md` exactly. Key constraint from architecture:

- `EnvironmentFile=` is the SOLE secret loading mechanism — never put `PICO_VOICE_ACCESS_KEY` in the unit file or `config.toml`
- `WorkingDirectory=/home/pi/pomodoro-bot` — the frozen binary reads `config.toml` relative to CWD; this directory must contain `config.toml`, `models/`, `.env`
- `User=pi` — standard Pi 5 user; confirm Pi 5 has `pi` user or adapt
- `After=sound.target` — audio initialization must precede process start

### Performance Gate Context

**Phase 1 gate is a hard AND condition:**
- `tok_per_sec >= 10.0` — LLM throughput gate
- `e2e_ms <= 25000` — full pipeline latency gate (wake-word → first spoken word)

Both must be true simultaneously before Phase 2 starts. The `PipelineMetrics` JSON format (from Story 2.1):
```json
{"event": "pipeline_metrics", "stt_ms": N, "llm_ms": N, "tts_ms": N, "tokens": N, "tok_per_sec": F, "e2e_ms": N}
```

**Mac results from Story 2.3** (reference, NOT gate check — Mac ≫ Pi 5 speed):
| Variant | Threads | tok/s (Mac) | e2e_ms (Mac) |
|---------|---------|-------------|--------------|
| Q4_K_M | 4 | 51.95 | 3696 |
| Q5_K_M | 4 | 44.00 | 4363 |
| Q8_0 | 4 | 41.80 | 4593 |

**Pi 5 expectations:** Significantly slower than Mac. `Qwen3-1.7B-Q4_K_M` at `n_threads=3-4` is the most likely gate-passing configuration based on architecture recommendations. The 0.6B model in `pi5-speed.json` achieved ~96 tok/s on Mac (Mac-speed, not Pi 5). Pi 5 throughput will be in the 10–25 tok/s range for 1.7B models.

### Critical Architectural Constraints for Runbook

**CPU core assignment (from architecture + project-context.md):**
- STT → core 0 (`cpu_cores = [0]`)
- LLM → cores 1–2 (`cpu_cores = [1, 2]`)
- TTS → core 3 (`cpu_cores = [3]`)
- `cpu_affinity_mode = "pinned"` must be set in `[llm]` section

**Never relax these in the runbook:**
- `compute_type = "int8"` — Pi 5 CPU (Cortex-A76) non-negotiable
- `vad_filter = true` — latency-critical; disabling multiplies STT invocations
- `n_threads` must be explicitly specified (no auto-detect)
- `multiprocessing.get_context("spawn")` — already enforced in code; runbook should mention it as a deployment invariant

**Pi 5 CPU governor:**
- Must run `./scripts/pi5_cpu_tuning.sh apply` BEFORE benchmarking
- Without it, CPU frequency-scaling causes throughput variance that makes gate verification unreliable

### Guard Test Compliance

`test_contract_guards.py` scans: `workers/llm.py`, `workers/stt.py`, `workers/tts.py`, `utterance.py`, `dispatch.py`, `calendar.py`, `ui.py`.

The new files created by this story (`dist/pomodoro-bot.service`, `docs/pi5-verification-runbook.md`) are:
- Not in any guarded Python source path
- Not Python files — no `from __future__ import annotations` required
- Zero risk of guard violations

### `from __future__ import annotations` Compliance (Epic 1 retro action #1)

No Python files are created or modified in the dev agent phase of this story. The only deliverables are:
- `dist/pomodoro-bot.service` — INI format, not Python
- `docs/pi5-verification-runbook.md` — Markdown, not Python

If any Python file is touched (unlikely), verify `from __future__ import annotations` is the first non-comment line.

### Tag and Commit Protocol (Operator section)

From architecture: CI/CD triggers on `git push --tags v*`. The tag `v1.0.0-phase1-verified` will trigger the GitHub Actions release workflow (`.github/workflows/release.yml`) which:
1. Builds a native arm64 binary in QEMU-emulated ARM64 container
2. Creates a GitHub Release with `archive-arm64.tar.gz`

The commit message format for Pi 5 results:
```
perf: pi5 gate verified — Q4_K_M n_threads=3 tok/s=12.4 e2e=18500ms
```
(Exact numbers will come from the actual Pi 5 sweep)

### Project Structure Notes

**Files to create (dev agent):**
- `dist/pomodoro-bot.service` — systemd unit file; committed to repo so it ships in the release tarball
- `docs/pi5-verification-runbook.md` — operator runbook; linked from `docs/deployment-guide.md`

**Files to update (operator, after Pi 5 verification):**
- `build/benchmark_results.json` — overwrite with Pi 5 sweep results

**No changes to `src/`** — all Phase 1 implementation is complete; this story is verification + deployment only.

### References

- Epics: `_bmad-output/planning-artifacts/epics.md` — Story 2.4 acceptance criteria (FR37, FR38, FR39, NFR-P1, NFR-P2)
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — Infrastructure & Deployment section: "Runtime service: systemd unit; EnvironmentFile= for secrets"; "Phase 1 performance gate is a hard AND condition"
- Deployment guide: `docs/deployment-guide.md` — systemd service template (lines 128–145), Pi 5 recommended config (lines 168–190), environment variables reference
- Epic 1 retro: `_bmad-output/implementation-artifacts/epic-1-retro-2026-03-01.md` — "dev agent delivers systemd service + deployment runbook; Shrink0r manually verifies performance gates on Pi 5"
- Story 2.3: `_bmad-output/implementation-artifacts/2-3-llm-model-sweep-benchmark-tooling.md` — Mac sweep results (Q4_K_M/4-threads = 51.95 tok/s), `scripts/pi5_model_sweep.py` usage
- Story 2.1: `_bmad-output/implementation-artifacts/2-1-pipelinemetrics-typed-dataclass-structured-json-log-emission.md` — PipelineMetrics JSON format
- Mac benchmark results: `build/benchmark_results.json` — 9 Mac entries (reference only, not Pi 5 gate data)
- Project context: `_bmad-output/project-context.md` — tech stack, CPU core assignment rules, config patterns

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- ✅ Created `dist/pomodoro-bot.service` — INI-format systemd unit file matching the exact template from `docs/deployment-guide.md` lines 128–145. All required directives present: `EnvironmentFile=`, `WorkingDirectory=`, `User=pi`, `Restart=on-failure`, `RestartSec=5`, `After=sound.target network.target`. No secrets hardcoded — all secrets loaded via `EnvironmentFile=/home/pi/pomodoro-bot/.env`.
- ✅ Created `docs/pi5-verification-runbook.md` — comprehensive 7-section operator runbook covering: prerequisites (libasound2, model layouts, pvporcupine version check), CPU governor application, benchmark sweep command (Q4_K_M × Q5_K_M × Q8_0 × threads 2,3,4), gate verification via `journalctl | grep pipeline_metrics`, `config.toml` update procedure for optimal variant/threads, systemd service install steps, and commit/tag protocol (`v1.0.0-phase1-verified`). Includes Pi 5 recommended config snippet and troubleshooting section.
- ✅ Full test suite: 168/168 tests pass, zero regressions. 13/13 contract guard tests pass. No structural violations introduced — new files are INI/Markdown, outside all guarded Python source paths.
- ℹ️ Operator tasks (Pi 5 hardware) left open per story scope boundary — Shrink0r executes when Pi 5 is available. Story status set to `review` for dev-agent deliverables only.
- 🔧 Code review fixes applied (2026-03-01): (1) Fixed `.gitignore` — `dist` entry changed to `dist/*` with `!dist/pomodoro-bot.service` exception; `dist/pomodoro-bot.service` is now trackable and staged. (2) Added `.gitignore` exceptions for `build/benchmark_results.json` and `build/pi5_gate_evidence.txt`. (3) Fixed `build.sh` — corrected tarball name to `archive.tar.gz` (was `pomodoro-bot-release.tar.gz`, mismatching CI expectation); added staging step to include service file, scripts, `pyproject.toml`, and `uv.lock` in release archive. (4) Added Pi 5 `uv` and virtualenv setup step (§1.6) to runbook before benchmark sweep. (5) Fixed f-string quote nesting in runbook Step 3 inspect script for Python 3.11 compatibility.
- 🔧 Code review fixes applied (2026-03-01, round 2): (H1/M2) Fixed `build.sh:39` — changed `rm -rf build dist` to `rm -rf build dist/main dist/stage dist/archive.tar.gz` so `dist/pomodoro-bot.service` is preserved during builds and PyInstaller cleanup does not destroy benchmark results in `build/`. (H2) Fixed `.gitignore:11` — changed `build` to `build/*` so `!build/benchmark_results.json` and `!build/pi5_gate_evidence.txt` exceptions are effective (git check-ignore confirmed). (M1) Fixed `docs/pi5-verification-runbook.md:173` — escaped `"` in `print(f"..."` header line to `print(f\"...\")` so the inspect script runs without shell syntax error inside `python3 -c "..."`.

### File List

- `dist/pomodoro-bot.service` (new) — systemd unit file for Pi 5 deployment
- `docs/pi5-verification-runbook.md` (new) — Pi 5 operator verification runbook
- `.gitignore` (modified) — changed `dist` → `dist/*` with `!dist/pomodoro-bot.service` exception; added `!build/benchmark_results.json` and `!build/pi5_gate_evidence.txt` exceptions so benchmark results can be committed; removed redundant `build` directory entry that was overriding `build/*` and breaking exceptions
- `build.sh` (modified) — fixed tarball name (`pomodoro-bot-release.tar.gz` → `archive.tar.gz` matching CI expectation); added staging step to include `dist/pomodoro-bot.service`, `scripts/pi5_cpu_tuning.sh`, `scripts/pi5_model_sweep.py`, `pyproject.toml`, `uv.lock` in the release archive; scoped PyInstaller cleanup to `rm -rf build dist/main dist/stage dist/archive.tar.gz` (preserves `dist/pomodoro-bot.service` and `build/benchmark_results.json`)
- `scripts/pi5_model_sweep.py` (modified) — added `--variant-names` CLI arg (positional label mapping to `--models`); added `--output-path` CLI arg with default `build/benchmark_results.json`; added `_write_benchmark_results()` for AC-schema JSON output; changed `BenchmarkResult.finish_reasons` from `dict` to `tuple` (frozen value object compliance); added `_PI5_EPILOG` help text; added `_extract_variant()` helper

## Change Log

- 2026-03-01: Dev agent deliverables complete — created `dist/pomodoro-bot.service` and `docs/pi5-verification-runbook.md`; 168/168 tests pass. Story set to `review`. Operator tasks (Pi 5 gate verification) deferred to Shrink0r when device available.
- 2026-03-01: Code review complete (round 2) — fixed 4 issues (2 HIGH, 2 MEDIUM): `build.sh` cleanup scope, `.gitignore` `build/*` pattern, runbook f-string escaping. Status set to `in-progress` (operator Pi 5 tasks remain open).
- 2026-03-02: Code review complete (round 3) — fixed 3 issues: [H1] removed redundant `.gitignore:12` `build` entry that was overriding `build/*` and making `!build/...` exceptions ineffective (confirmed via `git check-ignore`); [M1] added `scripts/pi5_model_sweep.py` to File List (was modified but undocumented); [M2] updated stale test count from 168 → 193 in AC#4 and task list (Epic 3 tests added in same commit batch). Status remains `in-progress` (operator Pi 5 tasks still deferred).
- 2026-03-02: Operator tasks confirmed complete by Shrink0r — Pi 5 performance gates verified (tok_per_sec ≥ 10.0, e2e_ms ≤ 25,000), model sweep run, results committed, `config.toml` updated with optimal values, service installed and running, repository tagged `v1.0.0-phase1-verified`. Story status set to `done`. Phase 1 AND gate fully satisfied; Phase 2 work (Epics 3 & 4) unlocked.

# Pi 5 Phase 1 Performance Gate Verification Runbook

> **Owner:** Shrink0r (operator)
> **Prerequisite:** Dev agent deliverables complete (Story 2.4) — `dist/pomodoro-bot.service` and this runbook are committed.
> **Goal:** Verify `tok_per_sec >= 10.0` AND `e2e_ms <= 25000` on real Pi 5 hardware, then tag `v1.0.0-phase1-verified`.

---

## Phase 1 Gate Conditions (AND — all three must be true)

| Condition | Threshold | Where verified |
|-----------|-----------|----------------|
| LLM throughput | `tok_per_sec >= 10.0` | `PipelineMetrics` JSON in systemd journal |
| Pipeline latency | `e2e_ms <= 25000` | `PipelineMetrics` JSON in systemd journal |
| All Epic 1 tests pass | zero failures | `uv run pytest tests/` on dev machine ✅ |

---

## Step 1 — Prerequisites

### 1.1 Hardware & OS

```bash
# Verify Pi 5 running Debian Bookworm (64-bit)
uname -m          # must show: aarch64
cat /etc/os-release | grep VERSION
```

### 1.2 System Dependencies

```bash
sudo apt update
sudo apt install -y libasound2
```

### 1.3 Install Directory Layout

The released tarball extracts to `/home/pi/pomodoro-bot/`. After extraction the layout must be:

```
/home/pi/pomodoro-bot/
  main                         ← frozen arm64 binary (from GitHub release archive-arm64.tar.gz)
  config.toml                  ← runtime config (edit per Step 4)
  .env                         ← secrets file (PICO_VOICE_ACCESS_KEY=...)
  dist/pomodoro-bot.service    ← included in release tarball
  scripts/
    pi5_cpu_tuning.sh
    pi5_model_sweep.py
  models/
    sst/
      hey-pomo.ppn             ← Picovoice wake-word model (version-matched)
      porcupine_params_de.pv   ← Picovoice language model (version-matched)
    llm/
      qwen/
        Qwen3-1.7B-Q4_K_M.gguf
        Qwen3-1.7B-Q5_K_M.gguf
        Qwen3-1.7B-Q8_0.gguf
    tts/
      thorsten-piper/          ← Piper TTS ONNX model directory
```

### 1.4 Picovoice Model File Version Check

> **Critical:** `.ppn` and `.pv` files must match the `pvporcupine` version in `pyproject.toml` exactly. Version mismatch causes silent wrong behaviour or crashes.

```bash
# Confirm pvporcupine version expected by binary
grep pvporcupine /home/pi/pomodoro-bot/pyproject.toml 2>/dev/null || \
  echo "Check pvporcupine version from release notes"

# Regenerate .ppn and .pv from Picovoice Console if version changed
# https://console.picovoice.ai/
```

### 1.5 Secrets File

```bash
# Create .env if not present
cat > /home/pi/pomodoro-bot/.env <<'EOF'
PICO_VOICE_ACCESS_KEY=<your-picovoice-key>
EOF
chmod 600 /home/pi/pomodoro-bot/.env
```

Verify no secrets appear in `config.toml`:
```bash
grep -i "PICO_VOICE\|ACCESS_KEY\|token\|password\|secret" /home/pi/pomodoro-bot/config.toml && \
  echo "WARNING: secret found in config.toml" || echo "OK: no secrets in config.toml"
```

### 1.6 Install Python Environment for Benchmark Tools

The benchmark sweep script (`scripts/pi5_model_sweep.py`) requires `llama-cpp-python` and runs via `uv`. Install `uv` if not already present, then set up the project virtualenv:

```bash
# Install uv (if not present)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env  # or restart shell

cd /home/pi/pomodoro-bot
uv sync --frozen
```

> The `scripts/` directory and `pyproject.toml` are included in the release tarball alongside the frozen binary.

### 1.7 Download All Three GGUF Variants

If variants are not yet present, download from HuggingFace:

```bash
pip install huggingface_hub
mkdir -p /home/pi/pomodoro-bot/models/llm/qwen

python3 -c "
from huggingface_hub import hf_hub_download
repo = 'lm-kit/qwen-3-1.7b-instruct-gguf'
dest = '/home/pi/pomodoro-bot/models/llm/qwen'
for f in ['Qwen3-1.7B-Q4_K_M.gguf', 'Qwen3-1.7B-Q5_K_M.gguf', 'Qwen3-1.7B-Q8_0.gguf']:
    print(f'Downloading {f}...')
    hf_hub_download(repo_id=repo, filename=f, local_dir=dest)
print('Done.')
"
```

---

## Step 2 — Apply CPU Performance Governor

> **Mandatory before benchmarking.** Without this, CPU frequency-scaling causes throughput variance that makes gate verification unreliable.

```bash
cd /home/pi/pomodoro-bot
sudo ./scripts/pi5_cpu_tuning.sh apply

# Verify governor applied
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
# Expected output: performance (4 lines)
```

The governor resets to `ondemand` on reboot. Re-apply before each benchmark session.

---

## Step 3 — Run Model Sweep Benchmark

> Sweep: Q4_K_M × Q5_K_M × Q8_0 × threads {2, 3, 4} = 9 combinations, 3 measured runs each.

```bash
cd /home/pi/pomodoro-bot

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

> **Expected duration:** 30–90 minutes on Pi 5 depending on model/threads.
> The script writes progress to stdout. Results are appended/replaced in `build/benchmark_results.json`.

### Inspect Results

```bash
python3 -c "
import json, sys
data = json.load(open('build/benchmark_results.json'))
# Sort by tok_per_sec descending
sorted_data = sorted(data, key=lambda x: x['tok_per_sec'], reverse=True)
print(f\"{'Variant':<12} {'Threads':>7} {'tok/s':>8} {'e2e_ms':>9} {'Gate':>6}\")
print('-' * 50)
for e in sorted_data:
    gate = '✅' if e['tok_per_sec'] >= 10.0 and e['e2e_ms'] <= 25000 else '❌'
    print(f\"{e['model_variant']:<12} {e['n_threads']:>7} {e['tok_per_sec']:>8.2f} {e['e2e_ms']:>9} {gate:>6}\")
"
```

### Identify Optimal Configuration

Select the entry with:
- `tok_per_sec >= 10.0` (mandatory)
- `e2e_ms <= 25000` (mandatory)
- Highest `tok_per_sec` among passing entries (prefer lower quantization loss if tied)

Note down the **variant** and **n_threads** for the optimal entry.

---

## Step 4 — Update `config.toml` for Optimal Configuration

Edit `/home/pi/pomodoro-bot/config.toml` to apply the optimal model and thread count.

**Recommended Pi 5 `config.toml` (update highlighted fields):**

```toml
[stt]
model_size = "base"
compute_type = "int8"      # non-negotiable for Pi 5 Cortex-A76
cpu_threads = 2
beam_size = 1
vad_filter = true          # never disable — latency-critical
cpu_cores = [0]            # STT pinned to core 0

[llm]
# ↓ Update these two fields from benchmark results
hf_filename = "Qwen3-1.7B-Q4_K_M.gguf"   # replace with optimal variant filename
n_threads = 3                               # replace with optimal n_threads
# ───────────────────────────────────────────
n_threads_batch = 3        # keep equal to n_threads
n_batch = 512
n_ctx = 2048
max_tokens = 128
cpu_affinity_mode = "pinned"
cpu_cores = [1, 2]         # LLM pinned to cores 1–2
fast_path_enabled = true

[tts]
cpu_cores = [3]            # TTS pinned to core 3
```

> **Invariant:** `multiprocessing.get_context("spawn")` is enforced in code — do not attempt to change to `fork` on Pi 5.

---

## Step 5 — Install and Start Systemd Service

```bash
# Copy service file from repo
sudo cp /home/pi/pomodoro-bot/dist/pomodoro-bot.service /etc/systemd/system/

# Reload systemd and enable/start the service
sudo systemctl daemon-reload
sudo systemctl enable pomodoro-bot
sudo systemctl restart pomodoro-bot

# Verify startup
sudo systemctl status pomodoro-bot
```

Expected status output should show `Active: active (running)`.

---

## Step 6 — Gate Verification via Journal

> Verify **both** gates across a minimum of **3 representative utterances**.
> Speak a natural command to trigger the full wake-word → STT → LLM → TTS pipeline each time.

### Watch the Journal

```bash
journalctl -u pomodoro-bot -f | grep pipeline_metrics
```

### Example `PipelineMetrics` JSON Output

```json
{"event": "pipeline_metrics", "stt_ms": 1200, "llm_ms": 14500, "tts_ms": 3100, "tokens": 45, "tok_per_sec": 12.4, "e2e_ms": 18800}
```

### Gate Check Per Entry

| Field | Gate | Pass condition |
|-------|------|----------------|
| `tok_per_sec` | `>= 10.0` | LLM throughput gate |
| `e2e_ms` | `<= 25000` | Full pipeline latency gate (wake-word → first spoken word) |

Both fields must pass on **all 3 utterances** to consider the gate verified.

### Capture Gate Evidence

```bash
# Capture 10 minutes of journal output for archiving
journalctl -u pomodoro-bot --since "10 minutes ago" | grep pipeline_metrics > \
  /home/pi/pomodoro-bot/build/pi5_gate_evidence.txt

cat /home/pi/pomodoro-bot/build/pi5_gate_evidence.txt
```

---

## Step 7 — Commit Pi 5 Results and Tag Release

Once both gates are confirmed:

### 7.1 Transfer Results to Dev Machine

```bash
# On dev machine (replace PI_IP with actual IP)
scp pi@PI_IP:/home/pi/pomodoro-bot/build/benchmark_results.json build/benchmark_results.json
scp pi@PI_IP:/home/pi/pomodoro-bot/build/pi5_gate_evidence.txt build/pi5_gate_evidence.txt
```

### 7.2 Commit Benchmark Results

Replace `<variant>`, `<N>`, `<X>`, and `<Y>` with actual values from the sweep:

```bash
git add build/benchmark_results.json build/pi5_gate_evidence.txt
git commit -m "perf: pi5 gate verified — <variant> n_threads=<N> tok/s=<X> e2e=<Y>ms"

# Example (fill in real numbers):
# git commit -m "perf: pi5 gate verified — Q4_K_M n_threads=3 tok/s=12.4 e2e=18800ms"
```

### 7.3 Tag and Push

```bash
git tag v1.0.0-phase1-verified
git push origin main
git push --tags
```

> **Note:** Pushing the `v1.0.0-phase1-verified` tag triggers the GitHub Actions release workflow (`.github/workflows/release.yml`), which builds a native arm64 binary in a QEMU-emulated ARM64 container and creates a GitHub Release with `archive-arm64.tar.gz`.

---

## Troubleshooting

### Service Fails to Start

```bash
sudo journalctl -u pomodoro-bot -n 50 --no-pager
```

Common causes:
- `PICO_VOICE_ACCESS_KEY` missing from `.env` — check `EnvironmentFile=/home/pi/pomodoro-bot/.env` exists and is readable by `pi` user
- `WorkingDirectory` not found — ensure `/home/pi/pomodoro-bot/` exists with correct ownership
- Model files missing — verify `models/sst/hey-pomo.ppn` and `models/sst/porcupine_params_de.pv` are present

### `PipelineMetrics` Not Appearing in Journal

- Ensure wake-word detection is working (listen for `"hey pomo"` response)
- Verify LLM is enabled in `config.toml`: `[llm] enabled = true`
- STT VAD filter may reject very short utterances — speak clearly for 2+ seconds

### tok/s Below Gate Threshold

- Confirm CPU governor is set to `performance` (Step 2)
- Try reducing `n_threads` — on Pi 5, `n_threads=3` often outperforms `n_threads=4` due to OS scheduling
- Try lighter quantization variant (Q4_K_M over Q8_0) if throughput is the bottleneck

### e2e_ms Above Gate Threshold

- Check `vad_filter = true` is set — disabling it multiplies STT invocations significantly
- Check `beam_size = 1` in `[stt]` — higher values increase STT latency
- Confirm `cpu_affinity_mode = "pinned"` and correct `cpu_cores` per worker

---

## References

- Deployment guide: `docs/deployment-guide.md` — systemd service install, environment variables
- Benchmark script: `scripts/pi5_model_sweep.py --help`
- CPU tuning: `scripts/pi5_cpu_tuning.sh`
- Story 2.4 AC: `_bmad-output/implementation-artifacts/2-4-phase-1-performance-gate-verification-on-pi-5.md`
- Architecture: `_bmad-output/planning-artifacts/architecture.md` — Phase 1 performance gate definition
- Mac benchmark reference results: `build/benchmark_results.json` (Q4_K_M/4-threads = 51.95 tok/s on Mac)

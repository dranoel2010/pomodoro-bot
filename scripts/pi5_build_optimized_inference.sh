#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

if [ "${1:-}" = "--help" ]; then
  cat <<'USAGE'
Build llama-cpp-python from source with Raspberry Pi 5 CPU-oriented flags.

Usage:
  scripts/pi5_build_optimized_inference.sh

Notes:
- Run on Raspberry Pi OS 64-bit.
- Requires internet access and build dependencies.
USAGE
  exit 0
fi

if [ "$(uname -s)" != "Linux" ]; then
  echo "This script targets Linux (Raspberry Pi OS)." >&2
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

echo "[1/4] Installing native build prerequisites (requires sudo)..."
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y \
    build-essential \
    cmake \
    pkg-config \
    libopenblas-dev \
    libomp-dev \
    python3-dev
else
  echo "apt-get not found; install native build deps manually." >&2
fi

echo "[2/4] Syncing Python dependencies..."
UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}" uv sync --frozen

echo "[3/4] Rebuilding llama-cpp-python with Pi 5 optimization flags..."
export FORCE_CMAKE=1
export CMAKE_BUILD_TYPE=Release
export CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS -DGGML_OPENMP=ON -DGGML_NATIVE=ON -DGGML_LTO=ON"
UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}" uv pip install \
  --python .venv/bin/python \
  --no-binary llama-cpp-python \
  --force-reinstall \
  llama-cpp-python

echo "[4/4] Verifying installation..."
UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}" uv run python -c 'import llama_cpp; print("llama-cpp-python", llama_cpp.__version__)'

echo "Done. llama-cpp-python rebuilt for Pi 5 CPU throughput."

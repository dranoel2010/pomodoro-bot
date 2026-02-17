#!/bin/sh
set -eu

cd "$(dirname "$0")"

VENV_NAME="${VENV_NAME:-.venv}"

ENV_ERROR="This project requires Python >= 3.10 and uv to be installed."

if ! command -v python3 >/dev/null 2>&1; then
  echo "$ENV_ERROR" >&2
  exit 1
fi

PY_OK="$(python3 -c 'import sys; print(int(sys.version_info >= (3,10)))' 2>/dev/null || echo 0)"
if [ "$PY_OK" != "1" ]; then
  echo "$ENV_ERROR" >&2
  python3 -V >&2 || true
  exit 1
fi

UV_BIN=""
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(command -v uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
  UV_BIN="$HOME/.local/bin/uv"
fi

if [ -z "$UV_BIN" ]; then
  echo "uv is not installed." >&2
  echo "Install it from: https://docs.astral.sh/uv/getting-started/installation/" >&2
  echo "$ENV_ERROR" >&2
  exit 1
fi

if [ -f "uv.lock" ]; then
  echo "Syncing dependencies from uv.lock into $VENV_NAME..."
  "$UV_BIN" sync --frozen
else
  echo "No uv.lock found; resolving and syncing dependencies into $VENV_NAME..."
  "$UV_BIN" sync
fi

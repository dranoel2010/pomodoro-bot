#!/bin/sh
set -eu

cd "$(dirname "$0")"

ENV_ERROR="This project requires Python >= 3.11 and uv to be installed."

if ! command -v python3 >/dev/null 2>&1; then
  echo "$ENV_ERROR" >&2
  exit 1
fi

PY_OK="$(python3 -c 'import sys; print(int(sys.version_info >= (3,11)))' 2>/dev/null || echo 0)"
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

# Install exactly locked dependencies into .venv
"$UV_BIN" sync --frozen

# Clean PyInstaller artifacts
rm -f main.spec
rm -rf build dist
mkdir -p dist

# Build onefile binary
"$UV_BIN" run pyinstaller \
  --clean -y \
  --onefile \
  --name main \
  --add-data "web_ui/*:web_ui" \
  --collect-data llama_cpp \
  --collect-binaries llama_cpp \
  --collect-data pvporcupine \
  --collect-binaries pvporcupine \
  --collect-binaries pvrecorder \
  --collect-submodules TTS \
  src/main.py

BIN="dist/main"
[ -f "dist/main.exe" ] && BIN="dist/main.exe"

cp config.toml dist/config.toml
cp .env.dist dist/.env
cp -rf web_ui dist/web_ui

tar -C dist -czvf dist/archive.tar.gz "$(basename "$BIN")" config.toml .env web_ui

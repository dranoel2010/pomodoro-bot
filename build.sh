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

# Generate a deterministic PyInstaller spec that excludes bundled libstdc++.
cat > main.spec <<'SPEC'
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_submodules

datas = [('web_ui', 'web_ui')]
binaries = []
hiddenimports = []
datas += collect_data_files('llama_cpp')
datas += collect_data_files('pvporcupine')
binaries += collect_dynamic_libs('llama_cpp')
binaries += collect_dynamic_libs('pvporcupine')
binaries += collect_dynamic_libs('pvrecorder')
hiddenimports += collect_submodules('TTS')

_EXCLUDED_LIB_BASENAMES = {"libstdc++.so.6"}


def _is_excluded_binary(entry) -> bool:
    names = []
    for part in entry[:2]:
        if isinstance(part, str):
            names.append(Path(part).name)
    return any(
        name in _EXCLUDED_LIB_BASENAMES or name.startswith("libstdc++.so.6.")
        for name in names
    )


a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.binaries = [entry for entry in a.binaries if not _is_excluded_binary(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
SPEC

# Build onefile binary from the generated spec.
"$UV_BIN" run pyinstaller --clean -y main.spec

BIN="dist/main"
[ -f "dist/main.exe" ] && BIN="dist/main.exe"

cp config.toml dist/config.toml
cp .env.dist dist/.env
cp -rf web_ui dist/web_ui

tar -C dist -czvf dist/archive.tar.gz "$(basename "$BIN")" config.toml .env web_ui

#/bin/sh

source .env
source .venv/bin/activate

uv run python src/main.py

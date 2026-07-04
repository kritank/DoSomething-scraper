#!/usr/bin/env bash
set -euo pipefail

REAL_PYTHON="/Users/kritank/.local/share/uv/python/cpython-3.13.14-macos-aarch64-none/bin/python3.13"
SITE_PACKAGES=".venv/lib/python3.13/site-packages"

if [ ! -x "$REAL_PYTHON" ] || [ ! -d "$SITE_PACKAGES" ]; then
  cat <<'EOF'
Virtual environment not found.

Run:
  UV_CACHE_DIR=/private/tmp/uv-cache uv venv --python 3.13.14 .venv
  UV_CACHE_DIR=/private/tmp/uv-cache uv sync --python 3.13.14
EOF
  exit 1
fi

export PYTHONPATH="$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
PORT="${PORT:-8000}"
exec "$REAL_PYTHON" -m uvicorn main:app --reload --port "$PORT"

#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_NAME="${1:-}"
shift || true

if [[ -z "$VENV_NAME" ]]; then
  echo "[run_py] Missing venv name (expected .venv-webscraper)" >&2
  exit 2
fi

PY="$REPO_ROOT/$VENV_NAME/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[run_py] Python not found/executable: $PY" >&2
  exit 2
fi

echo "[run_py] Using Python: $PY"
exec "$PY" "$@"

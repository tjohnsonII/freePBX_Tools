#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VENV_REL="${1:-}"
if [ -z "$VENV_REL" ]; then
  echo "ERROR: Missing venv path argument." >&2
  exit 1
fi
shift || true

PY="${REPO_ROOT}/${VENV_REL}/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: Python not found: $PY" >&2
  exit 1
fi

echo "[run_py] Using Python: $PY"

if [ "$#" -eq 0 ]; then
  exec "$PY" -V
fi

exec "$PY" "$@"

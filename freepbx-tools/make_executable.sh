#!/usr/bin/env bash
# Backward-compatibility wrapper. Historically README references make_executable.sh.
# The canonical script is now bootstrap.sh.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${DIR}/bootstrap.sh"

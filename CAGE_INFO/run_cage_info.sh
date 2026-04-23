#!/bin/bash
set -euo pipefail

LOG="cage_output_$(date +%F_%H%M%S).log"

./cage_info.sh | tee "$LOG"

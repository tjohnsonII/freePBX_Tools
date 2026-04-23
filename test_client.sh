#!/usr/bin/env bash
# test_client.sh — three-level test suite for CLIENT_MODE
#
# LEVEL 1 (always):   pytest unit tests — no server needed
# LEVEL 2 (auto):     smoke tests against a live server
#                     requires INGEST_SERVER_URL + INGEST_API_KEY to be set
# LEVEL 3 (--e2e):    start client API, queue a scrape job, verify it reaches server
#                     requires all level-2 env vars + --e2e flag
#
# Usage:
#   ./test_client.sh                # levels 1 + 2
#   ./test_client.sh --e2e          # levels 1 + 2 + 3
#   ./test_client.sh --no-color     # disable ANSI colours

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
WEBSCRAPER_DIR="$REPO_ROOT/webscraper"
VENV="$WEBSCRAPER_DIR/.venv-webscraper"

# Load .env if present (same as start_client.sh)
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$REPO_ROOT/.env"
  set +a
fi

# Prefer venv python, fall back to system python/py
if [[ -x "$VENV/Scripts/python" ]]; then
  PYTHON="$VENV/Scripts/python"
elif command -v python &>/dev/null; then
  PYTHON="python"
elif command -v py &>/dev/null; then
  PYTHON="py"
else
  echo "ERROR: No Python found. Install Python or create the venv first."
  exit 1
fi

# ── Args ──────────────────────────────────────────────────────────────────────
RUN_E2E=0
NO_COLOR=0
for arg in "$@"; do
  case "$arg" in
    --e2e)      RUN_E2E=1 ;;
    --no-color) NO_COLOR=1 ;;
  esac
done

# ── Color helpers ─────────────────────────────────────────────────────────────
_red()   { [[ $NO_COLOR -eq 1 ]] && echo "$*" || echo -e "\033[0;31m$*\033[0m"; }
_green() { [[ $NO_COLOR -eq 1 ]] && echo "$*" || echo -e "\033[0;32m$*\033[0m"; }
_cyan()  { [[ $NO_COLOR -eq 1 ]] && echo "$*" || echo -e "\033[0;36m$*\033[0m"; }
_bold()  { [[ $NO_COLOR -eq 1 ]] && echo -e "$*" || echo -e "\033[1m$*\033[0m"; }

PASS=0
FAIL=0
_pass() { _green "  ✓ $*"; PASS=$((PASS + 1)); }
_fail() { _red   "  ✗ $*"; FAIL=$((FAIL + 1)); }
_skip() { echo   "  - $* (skipped)"; }

# ── Prereq check ──────────────────────────────────────────────────────────────
echo "Using Python: $("$PYTHON" --version 2>&1)"

CLIENT_PORT="${CLIENT_PORT:-8789}"
CLIENT_PID=""

cleanup() {
  if [[ -n "$CLIENT_PID" ]]; then
    kill "$CLIENT_PID" 2>/dev/null || true
    wait "$CLIENT_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ── Helper: JSON field from curl response ─────────────────────────────────────
_json_field() {
  # _json_field <json_string> <key>  — naive but dependency-free
  echo "$1" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print(d.get('$2',''))"
}

_curl_json() {
  curl -s --max-time 10 "$@"
}

# ═════════════════════════════════════════════════════════════════════════════
_bold "\n══ LEVEL 1 — Unit tests (no server required) ══"
# ═════════════════════════════════════════════════════════════════════════════

cd "$WEBSCRAPER_DIR"

if "$PYTHON" -m pytest tests/test_client_mode.py -v --tb=short 2>&1; then
  _pass "All client-mode unit tests passed"
else
  _fail "Unit tests failed — fix before running higher levels"
  FAIL=1
  # Still print summary and exit
  _bold "\n── Summary ──────────────────────────────────────────────"
  echo "  Passed: $PASS   Failed: $FAIL"
  exit 1
fi

# ═════════════════════════════════════════════════════════════════════════════
_bold "\n══ LEVEL 2 — Server smoke tests ══"
# ═════════════════════════════════════════════════════════════════════════════

SERVER="${INGEST_SERVER_URL:-}"
KEY="${INGEST_API_KEY:-}"

if [[ -z "$SERVER" || -z "$KEY" ]]; then
  _skip "INGEST_SERVER_URL / INGEST_API_KEY not set — skipping level 2"
  _skip "  export INGEST_SERVER_URL=http://<server-ip>:8788"
  _skip "  export INGEST_API_KEY=<shared-secret>"
else
  SERVER="${SERVER%/}"

  # 2a — health
  HEALTH=$(_curl_json "$SERVER/api/health") || HEALTH=""
  if echo "$HEALTH" | grep -q '"ok"'; then
    _pass "Server health OK  ($SERVER/api/health)"
  else
    _fail "Server health check failed — is the server running?"
    echo "       Response: $HEALTH"
  fi

  # 2b — ingest with correct key
  INGEST_RESP=$(_curl_json -s -X POST "$SERVER/api/ingest/handles" \
    -H "X-Ingest-Key: $KEY" \
    -H "Content-Type: application/json" \
    -d '{"rows":[{"handle":"__TESTHANDLE__"}]}') || INGEST_RESP=""
  if echo "$INGEST_RESP" | grep -q '"inserted"'; then
    _pass "Ingest POST accepted by server"
  else
    _fail "Ingest POST failed — check INGEST_API_KEY matches server"
    echo "       Response: $INGEST_RESP"
  fi

  # 2c — ingest with wrong key returns 4xx
  STATUS=$(_curl_json -o /dev/null -w "%{http_code}" -X POST "$SERVER/api/ingest/handles" \
    -H "X-Ingest-Key: wrong-key" \
    -H "Content-Type: application/json" \
    -d '{"rows":[{"handle":"X"}]}') || STATUS=""
  if [[ "$STATUS" == "403" || "$STATUS" == "401" ]]; then
    _pass "Wrong key correctly rejected (HTTP $STATUS)"
  else
    _fail "Wrong key was NOT rejected — got HTTP $STATUS (expected 403)"
  fi

  # 2d — handle appears on server (use /all endpoint which supports q filter)
  HANDLES=$(_curl_json "$SERVER/api/handles/all?q=__TESTHANDLE__&limit=10") || HANDLES=""
  if echo "$HANDLES" | grep -q "__TESTHANDLE__"; then
    _pass "Ingested handle visible on server"
  else
    _fail "Handle not found on server after ingest"
    echo "       Response: $HANDLES"
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
_bold "\n══ LEVEL 3 — End-to-end (client API + scrape job) ══"
# ═════════════════════════════════════════════════════════════════════════════

if [[ $RUN_E2E -eq 0 ]]; then
  _skip "Pass --e2e to run level 3"
elif [[ -z "$SERVER" || -z "$KEY" ]]; then
  _skip "INGEST_SERVER_URL / INGEST_API_KEY not set — cannot run level 3"
else
  # 3a — start client API in background
  export CLIENT_MODE=1
  export INGEST_SERVER_URL="$SERVER"
  export INGEST_API_KEY="$KEY"

  # Seed a minimal handles file so /api/scrape/start has at least one handle.
  # Uses webscraper/var/handles.txt (the fallback path in handles_loader.py).
  HANDLES_DIR="$WEBSCRAPER_DIR/var"
  HANDLES_TXT="$HANDLES_DIR/handles.txt"
  HANDLES_TXT_CREATED=0
  mkdir -p "$HANDLES_DIR"
  if [[ ! -f "$HANDLES_TXT" ]]; then
    echo "__TESTHANDLE__" > "$HANDLES_TXT"
    HANDLES_TXT_CREATED=1
  fi

  "$PYTHON" -m uvicorn webscraper.ticket_api.app:app \
    --host 127.0.0.1 --port "$CLIENT_PORT" --app-dir src \
    > /tmp/test_client_uvicorn.log 2>&1 &
  CLIENT_PID=$!

  # Wait for /healthz (up to 15s)
  READY=0
  for i in $(seq 1 15); do
    sleep 1
    if _curl_json "http://127.0.0.1:$CLIENT_PORT/healthz" 2>/dev/null | grep -q '"ok"'; then
      READY=1
      break
    fi
  done

  if [[ $READY -eq 0 ]]; then
    _fail "Client API did not start within 15s (port $CLIENT_PORT)"
    echo "       Log: $(cat /tmp/test_client_uvicorn.log 2>/dev/null | tail -5)"
  else
    _pass "Client API started on port $CLIENT_PORT"

    # 3b — queue a scrape job
    JOB_RESP=$(_curl_json -X POST "http://127.0.0.1:$CLIENT_PORT/api/scrape/start") || JOB_RESP=""
    JOB_ID=$(echo "$JOB_RESP" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); print(d.get('job_id',''))" 2>/dev/null || true)

    if [[ -n "$JOB_ID" ]]; then
      _pass "Scrape job queued on client  (job_id=$JOB_ID)"
    else
      _fail "Failed to queue scrape job"
      echo "       Response: $JOB_RESP"
    fi

    # 3c — job appears on server within 10s
    if [[ -n "$JOB_ID" ]]; then
      MIRRORED=0
      for i in $(seq 1 10); do
        sleep 1
        SERVER_JOB=$(_curl_json "$SERVER/api/jobs/$JOB_ID") || SERVER_JOB=""
        if echo "$SERVER_JOB" | grep -q '"job_id"'; then
          MIRRORED=1
          break
        fi
      done

      if [[ $MIRRORED -eq 1 ]]; then
        _pass "Job mirrored to server  (job_id=$JOB_ID)"
      else
        _fail "Job not visible on server after 10s — ingest may be failing silently"
        echo "       Check server logs for 403 errors from $KEY"
      fi
    fi
  fi

  # Stop client
  kill "$CLIENT_PID" 2>/dev/null || true
  CLIENT_PID=""

  # Remove the temporary handles file if we created it
  if [[ $HANDLES_TXT_CREATED -eq 1 ]]; then
    rm -f "$HANDLES_TXT"
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
_bold "\n── Summary ──────────────────────────────────────────────────"
echo "  Passed: $PASS   Failed: $FAIL"
if [[ $FAIL -eq 0 ]]; then
  _green "  All checks passed."
else
  _red   "  $FAIL check(s) failed."
fi
[[ $FAIL -eq 0 ]]

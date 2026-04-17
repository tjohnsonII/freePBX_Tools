#!/bin/bash
# auth_session.sh — launch a visible Chrome session on a virtual display for one-time SSO login.
#
# Usage:
#   ./scripts/auth_session.sh
#
# Then from your laptop:
#   ssh -L 5900:127.0.0.1:5900 <server>
# Open a VNC client pointed at localhost:5900 (no password by default).
# Log in to secure.123.net via SSO.  Close the browser when done — the profile is saved.
#
# After this, ticket scrapes will reuse the saved profile automatically
# (set WEBSCRAPER_CHROME_PROFILE_DIR=var/chrome-profile in the environment).

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE_DIR="$REPO/webscraper/var/chrome-profile"
DISPLAY_NUM=99
VNC_PORT=5900
TARGET_URL="https://secure.123.net/cgi-bin/web_interface/admin/customers.cgi"

mkdir -p "$PROFILE_DIR"

# ── Verify required tools ──────────────────────────────────────────────────
for tool in Xvfb x11vnc openbox google-chrome; do
    if ! command -v "$tool" &>/dev/null; then
        echo "[ERROR] '$tool' not found. Run: sudo apt install -y xvfb x11vnc openbox"
        [ "$tool" = "google-chrome" ] && echo "        For Chrome: see https://www.google.com/chrome/browser/desktop/"
        exit 1
    fi
done

# ── Kill any stale virtual display / VNC on our slot ─────────────────────
pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
pkill -f "x11vnc.*:${DISPLAY_NUM}" 2>/dev/null || true
sleep 1

# ── Start virtual display ─────────────────────────────────────────────────
echo "[auth] Starting Xvfb on :${DISPLAY_NUM} ..."
Xvfb ":${DISPLAY_NUM}" -screen 0 1280x900x24 &
XVFB_PID=$!
sleep 1

export DISPLAY=":${DISPLAY_NUM}"

# ── Start minimal window manager ─────────────────────────────────────────
openbox &
sleep 0.5

# ── Expose display via VNC (localhost-only, no password) ─────────────────
echo "[auth] Starting x11vnc on localhost:${VNC_PORT} ..."
x11vnc -display ":${DISPLAY_NUM}" -localhost -nopw -forever -bg -quiet
echo ""
echo "==========================================================="
echo "  VNC is ready on localhost:${VNC_PORT}"
echo ""
echo "  From your laptop, open an SSH tunnel:"
echo "    ssh -L ${VNC_PORT}:127.0.0.1:${VNC_PORT} $(hostname)"
echo ""
echo "  Then connect a VNC client to:  localhost:${VNC_PORT}"
echo "==========================================================="
echo ""

# ── Launch Chrome with persistent profile (NOT headless) ─────────────────
echo "[auth] Launching Chrome with profile: $PROFILE_DIR"
google-chrome \
    --user-data-dir="$PROFILE_DIR" \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --window-size=1280,900 \
    "$TARGET_URL" &
CHROME_PID=$!

echo "[auth] Chrome PID: $CHROME_PID"
echo "[auth] Log in via VNC, then close Chrome to save the session."
echo "[auth] Waiting for Chrome to exit..."
wait "$CHROME_PID" 2>/dev/null || true

echo ""
echo "[auth] Chrome closed.  Profile saved to: $PROFILE_DIR"
echo "[auth] Stopping virtual display..."

kill "$XVFB_PID" 2>/dev/null || true
pkill -f "x11vnc.*:${DISPLAY_NUM}" 2>/dev/null || true

echo "[auth] Done.  Run ticket scrapes normally — the saved session will be reused."

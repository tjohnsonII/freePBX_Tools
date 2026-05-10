#!/usr/bin/env bash
# check_client_connectivity.sh
# Verifies that ticket-api.123hostedtools.com is reachable from client machines
# by testing each layer: local uvicorn → Apache proxy → internal HTTPS → public HTTPS.
#
# Usage: ./scripts/check_client_connectivity.sh

set -uo pipefail

HOSTNAME="ticket-api.123hostedtools.com"
INTERNAL_IP="192.168.100.10"
HEALTH_PATH="/api/health"

PASS=0
FAIL=0

green='\033[0;32m'
red='\033[0;31m'
yellow='\033[0;33m'
reset='\033[0m'

ok()   { echo -e "  ${green}✓${reset}  $*"; PASS=$((PASS+1)); }
fail() { echo -e "  ${red}✗${reset}  $*"; FAIL=$((FAIL+1)); }
info() { echo -e "  ${yellow}→${reset}  $*"; }

echo ""
echo "════════════════════════════════════════════════"
echo "  ticket-api connectivity check"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════"

# ── 1. Uvicorn (raw backend) ──────────────────────────────────────────────────
echo ""
echo "[ 1 ] Local uvicorn  http://127.0.0.1:8788$HEALTH_PATH"
if curl -sf --max-time 5 "http://127.0.0.1:8788$HEALTH_PATH" -o /dev/null 2>/dev/null; then
    ok "uvicorn is up and responding"
else
    fail "uvicorn not responding on port 8788 — run: sudo ./RESTART.sh ticket-api"
fi

# ── 2. Apache reverse proxy (HTTP, internal) ──────────────────────────────────
echo ""
echo "[ 2 ] Apache proxy   http://127.0.0.1:80$HEALTH_PATH  (Host: $HOSTNAME)"
if curl -sf --max-time 5 \
        -H "Host: $HOSTNAME" \
        "http://127.0.0.1:80$HEALTH_PATH" -o /dev/null 2>/dev/null; then
    ok "Apache is proxying HTTP correctly"
else
    fail "Apache not proxying — check: sudo apache2ctl configtest && sudo systemctl status apache2"
fi

# ── 3. Internal HTTPS (what LAN clients hit after DNS resolves to 192.168.100.10) ─
# Uses --resolve to simulate a client whose DNS returns the internal IP for the
# hostname — SNI is sent correctly, avoiding the HTTP 421 that raw-IP + Host: causes.
echo ""
echo "[ 3 ] Internal HTTPS https://$HOSTNAME$HEALTH_PATH  (resolved to $INTERNAL_IP)"
HTTP_CODE=$(curl -sk --max-time 8 \
    --resolve "$HOSTNAME:443:$INTERNAL_IP" \
    -o /dev/null -w "%{http_code}" \
    "https://$HOSTNAME$HEALTH_PATH" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then
    ok "Internal HTTPS reachable (LAN clients on 192.168.x.x should work)"
elif [[ "$HTTP_CODE" == "000" ]]; then
    fail "Internal HTTPS timed out — check Apache SSL vhost and firewall (port 443 LAN→DMZ)"
else
    fail "Internal HTTPS returned HTTP $HTTP_CODE"
fi

# ── 4. DNS resolution (what external clients get) ────────────────────────────
echo ""
echo "[ 4 ] Public DNS     $HOSTNAME"
RESOLVED_IP=$(dig +short "$HOSTNAME" @8.8.8.8 2>/dev/null | head -1)
if [[ -z "$RESOLVED_IP" ]]; then
    fail "Public DNS did not resolve $HOSTNAME"
else
    info "Public DNS → $RESOLVED_IP"
    if [[ "$RESOLVED_IP" == "$INTERNAL_IP" ]]; then
        echo -e "  ${yellow}!${reset}  Resolves to internal IP — external clients will fail unless on LAN/VPN"
    else
        ok "Resolves to public IP ($RESOLVED_IP)"
    fi
fi

# ── 5. Public HTTPS (what internet clients hit) ───────────────────────────────
echo ""
echo "[ 5 ] Public HTTPS   https://$HOSTNAME$HEALTH_PATH"
PUB_CODE=$(curl -s --max-time 10 \
    -o /dev/null -w "%{http_code}" \
    "https://$HOSTNAME$HEALTH_PATH" 2>/dev/null || echo "000")
if [[ "$PUB_CODE" == "200" ]]; then
    ok "Public HTTPS reachable — any internet client can reach the API"
elif [[ "$PUB_CODE" == "000" ]]; then
    fail "Public HTTPS timed out — check port 443 forwarding on router and Apache SSL"
else
    fail "Public HTTPS returned HTTP $PUB_CODE"
fi

# ── 6. TLS certificate ────────────────────────────────────────────────────────
echo ""
echo "[ 6 ] TLS certificate for $HOSTNAME"
CERT_INFO=$(echo | openssl s_client -connect "$INTERNAL_IP:443" \
    -servername "$HOSTNAME" 2>/dev/null | openssl x509 -noout -dates 2>/dev/null || true)
if [[ -n "$CERT_INFO" ]]; then
    NOT_AFTER=$(echo "$CERT_INFO" | grep notAfter | cut -d= -f2)
    EXPIRY_TS=$(date -d "$NOT_AFTER" +%s 2>/dev/null || echo 0)
    NOW_TS=$(date +%s)
    DAYS_LEFT=$(( (EXPIRY_TS - NOW_TS) / 86400 ))
    if [[ $DAYS_LEFT -gt 14 ]]; then
        ok "Certificate valid for $DAYS_LEFT more days (expires $NOT_AFTER)"
    elif [[ $DAYS_LEFT -gt 0 ]]; then
        fail "Certificate expires in $DAYS_LEFT days — run: sudo certbot renew"
    else
        fail "Certificate EXPIRED — run: sudo certbot renew --force-renewal"
    fi
else
    fail "Could not retrieve TLS certificate from $INTERNAL_IP:443"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════"
TOTAL=$((PASS+FAIL))
if [[ $FAIL -eq 0 ]]; then
    echo -e "  ${green}ALL $TOTAL CHECKS PASSED${reset}"
    echo ""
    echo "  Client access:"
    echo "  • LAN (192.168.x.x / VPN): hosts file or internal DNS → $INTERNAL_IP"
    echo "  • Internet:                 https://$HOSTNAME"
else
    echo -e "  ${red}$FAIL / $TOTAL CHECKS FAILED${reset}"
    echo ""
    echo "  Fix the failures above, then re-run this script."
fi
echo "════════════════════════════════════════════════"
echo ""

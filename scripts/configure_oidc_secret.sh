#!/bin/bash
# Plug the Keycloak client secret into the OIDC config and reload Apache.
# Run after creating the client in Keycloak:
#   sudo bash scripts/configure_oidc_secret.sh
set -euo pipefail

OIDC_CONF=/etc/apache2/includes/oidc-common.conf

echo "Keycloak client secret configurator"
echo "===================================="
echo "Go to: https://auth.123hostedtools.com/admin/"
echo "Realm: internal-tools"
echo "Clients → apache-oidc → Credentials tab → copy the Secret"
echo ""
read -rsp "Paste the client secret here (input hidden): " SECRET
echo ""

if [ -z "$SECRET" ]; then
    echo "[error] Secret cannot be empty."
    exit 1
fi

sed -i "s|OIDCClientSecret .*|OIDCClientSecret ${SECRET}|" "$OIDC_CONF"
echo "[ok] Secret written to $OIDC_CONF"

apache2ctl configtest && systemctl reload apache2
echo "[ok] Apache reloaded — OIDC is now active on all protected vhosts."
echo ""
echo "Test login at: https://manager.123hostedtools.com"

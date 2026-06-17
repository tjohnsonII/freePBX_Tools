#!/bin/bash
set -e

# Files that exist ONLY on Server — must be added to main from Server.
SERVER_UNIQUE_FILES=(
    "webscraper/scripts/scrape_orders.py"
    "webscraper_manager/api/routes/orders.py"
    "webscraper_manager/requirements.txt"
    "webscraper_manager/api/server.py"
)

# Files that exist on BOTH branches but Server is authoritative
# (server has the superset — orders schema, enrichment tables, agent layer, etc.)
SERVER_AUTHORITATIVE_FILES=(
    "webscraper/src/webscraper/ticket_api/db.py"
    "webscraper/src/webscraper/ticket_api/db_client.py"
    "webscraper/src/webscraper/ticket_api/ingest_routes.py"
    "PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/src/HostedOrderTrackerTab.tsx"
)

REMOTE="${1:-origin}"
SERVER_BRANCH="Server"
CLIENT_BRANCH="client"

echo "=== Syncing main ==="
echo "Strategy: main = $CLIENT_BRANCH (base) + server-unique + server-authoritative files"
echo ""

git fetch "$REMOTE"

git checkout main

# Reset main to equal client — newest version of all client-side code
git reset --hard "$REMOTE/$CLIENT_BRANCH"
echo "  [ok] main reset to $REMOTE/$CLIENT_BRANCH"

# Overlay files that only exist on Server
echo ""
echo "Overlaying Server-unique files:"
for f in "${SERVER_UNIQUE_FILES[@]}"; do
    if git ls-tree -r "$REMOTE/$SERVER_BRANCH" --name-only | grep -qx "$f"; then
        git checkout "$REMOTE/$SERVER_BRANCH" -- "$f"
        echo "  [+] $f"
    else
        echo "  [-] $f — not found on $SERVER_BRANCH, skipping"
    fi
done

# Overlay files where Server is authoritative (superset of client version)
echo ""
echo "Overlaying Server-authoritative files:"
for f in "${SERVER_AUTHORITATIVE_FILES[@]}"; do
    if git ls-tree -r "$REMOTE/$SERVER_BRANCH" --name-only | grep -qx "$f"; then
        git checkout "$REMOTE/$SERVER_BRANCH" -- "$f"
        echo "  [+] $f"
    else
        echo "  [-] $f — not found on $SERVER_BRANCH, skipping"
    fi
done

# Commit only if something actually changed
if git diff --cached --quiet; then
    echo ""
    echo "No changes — main already up to date."
else
    echo ""
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    git commit -m "sync: main updated from $CLIENT_BRANCH + $SERVER_BRANCH files [$TIMESTAMP]"
    echo "  [ok] committed"
fi

git push --force "$REMOTE" main
echo "  [ok] pushed to $REMOTE/main"

git checkout -
echo ""
echo "Done. main is now the unified install-ready branch."

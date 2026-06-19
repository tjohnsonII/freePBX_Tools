#!/bin/bash
set -e

# Files that exist ONLY on Server — must be present on main.
SERVER_UNIQUE_FILES=(
    "webscraper/scripts/scrape_orders.py"
    "webscraper_manager/api/routes/orders.py"
    "webscraper_manager/requirements.txt"
    "webscraper_manager/api/server.py"
)

# Entire directories that exist ONLY on Server — all files overlaid onto main.
SERVER_UNIQUE_DIRS=(
    "lsbbw"
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
SERVER_BRANCH="server"
CLIENT_BRANCH="client"

echo "=== Syncing main ==="
echo "Strategy: main = $CLIENT_BRANCH (base) + server-unique + server-authoritative files"
echo ""

git fetch "$REMOTE"

# Build the unified tree using git plumbing — no checkout, no working-tree
# permission issues from root-owned files.
GIT_INDEX_FILE=$(mktemp /tmp/sync_idx.XXXXXX)
export GIT_INDEX_FILE

# Load client tree as base — newest version of all shared files
git read-tree "$REMOTE/$CLIENT_BRANCH"
echo "  [ok] loaded $REMOTE/$CLIENT_BRANCH as base"

# Overlay server files into the temporary index
echo ""
echo "Overlaying Server files:"
for f in "${SERVER_UNIQUE_FILES[@]}" "${SERVER_AUTHORITATIVE_FILES[@]}"; do
    INFO=$(git ls-tree "$REMOTE/$SERVER_BRANCH" -- "$f")
    if [ -n "$INFO" ]; then
        MODE=$(echo "$INFO" | awk '{print $1}')
        BLOB=$(echo "$INFO" | awk '{print $3}')
        git update-index --cacheinfo "$MODE,$BLOB,$f"
        echo "  [+] $f"
    else
        echo "  [-] $f — not found on $SERVER_BRANCH, skipping"
    fi
done

# Overlay entire server-unique directories
echo ""
echo "Overlaying Server directories:"
for d in "${SERVER_UNIQUE_DIRS[@]}"; do
    while IFS=$'\t' read -r mode type blob path; do
        git update-index --cacheinfo "$mode,$blob,$path"
        echo "  [+] $path"
    done < <(git ls-tree -r "$REMOTE/$SERVER_BRANCH" -- "$d")
done

# Write the composite tree and create a commit on top of current main
NEW_TREE=$(git write-tree)
PARENT=$(git rev-parse "$REMOTE/main")

if [ "$NEW_TREE" = "$(git rev-parse "$PARENT^{tree}")" ]; then
    echo ""
    echo "No changes — main already up to date."
else
    echo ""
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    NEW_COMMIT=$(git commit-tree "$NEW_TREE" -p "$PARENT" \
        -m "sync: main = $CLIENT_BRANCH base + $SERVER_BRANCH files [$TIMESTAMP]")
    git push --force "$REMOTE" "${NEW_COMMIT}:refs/heads/main"
    echo "  [ok] pushed → $NEW_COMMIT"
fi

rm -f "$GIT_INDEX_FILE"
unset GIT_INDEX_FILE

echo ""
echo "Done. main is now the unified install-ready branch."

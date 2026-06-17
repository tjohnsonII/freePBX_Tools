#!/bin/bash
set -e

# Files that live on Server branch but not on client.
# Add new Server-only files here when they're created.
SERVER_UNIQUE_FILES=(
    "webscraper/scripts/scrape_orders.py"
    "webscraper_manager/api/routes/orders.py"
    "webscraper_manager/requirements.txt"
    "webscraper_manager/api/server.py"
)

REMOTE="${1:-origin}"
SERVER_BRANCH="Server"
CLIENT_BRANCH="client"

echo "=== Syncing main ==="
echo "Strategy: main = $CLIENT_BRANCH (newest base) + $SERVER_BRANCH unique files"
echo ""

# Make sure local refs are up to date
git fetch "$REMOTE"

git checkout main

# Reset main to equal client — this is the "latest of everything shared"
git reset --hard "$REMOTE/$CLIENT_BRANCH"
echo "  [ok] main reset to $REMOTE/$CLIENT_BRANCH"

# Overlay Server-only files
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

# Commit only if something actually changed
if git diff --cached --quiet; then
    echo ""
    echo "No changes from $SERVER_BRANCH — main already up to date."
else
    echo ""
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    git commit -m "sync: main updated from $CLIENT_BRANCH + $SERVER_BRANCH unique files [$TIMESTAMP]"
    echo "  [ok] committed"
fi

git push --force "$REMOTE" main
echo "  [ok] pushed to $REMOTE/main"

# Return to wherever we came from
git checkout -
echo ""
echo "Done. main is now the unified install-ready branch."

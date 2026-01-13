#!/bin/bash
# start-app.sh - Automate starting the Vite dev server with all common network options

# Install dependencies if needed
echo "Installing dependencies..."
npm install

echo "Starting Vite dev server with all common network options:"
echo "  --host 0.0.0.0 (listen on all interfaces)"
echo "  --port 3000 (custom port)"
echo "  --open (open browser)"
echo "  --https (enable HTTPS if configured)"
echo "  --strictPort (fail if port is taken)"

echo "You can edit this script to change options as needed."

npm run dev -- \
  --host 0.0.0.0 \
  --port 3000 \
  --open \
  --strictPort

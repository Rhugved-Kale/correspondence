#!/usr/bin/env bash
# Correspondence launcher.
#
# Run this from the project root. It will:
#   1. Build the React frontend if frontend/dist doesn't exist or is stale.
#   2. Start the FastAPI server on http://localhost:8000.
#   3. Open the browser to the app.
#
# Missing .env or credentials.json? The browser-based setup wizard will
# walk you through providing them. You don't need to edit any files
# before launching.

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# --- preflight: just verify Python deps are installed ----------------------
#
# The launcher intentionally does NOT check for .env or credentials.json
# here. Those are handled at runtime by the in-browser setup wizard, so
# a first-time user can just clone the repo, run this, and follow the
# UI. The only thing we still check is Python deps, because a missing
# module produces a less obvious error than a friendly check.

if ! python3 -c "import fastapi, uvicorn, anthropic" 2>/dev/null; then
  echo "Python dependencies aren't installed yet."
  echo "Run: pip install -r backend/requirements.txt"
  exit 1
fi

# --- build the frontend if needed --------------------------------------------
#
# Rebuild if dist doesn't exist OR if any source file is newer than the
# build output. Cheap heuristic that catches the common cases without
# tracking every dependency.

FRONTEND_DIR="$ROOT/frontend"
DIST="$FRONTEND_DIR/dist"

need_build="no"
if [ ! -d "$DIST" ]; then
  need_build="yes"
else
  if [ -n "$(find "$FRONTEND_DIR/src" -newer "$DIST/index.html" -type f 2>/dev/null | head -n 1)" ]; then
    need_build="yes"
  fi
fi

if [ "$need_build" = "yes" ]; then
  echo "Building frontend..."
  cd "$FRONTEND_DIR"
  if [ ! -d "node_modules" ]; then
    echo "  Installing npm dependencies (one-time setup)..."
    npm install --silent
  fi
  npm run build --silent
  cd "$ROOT"
fi

# --- start the server --------------------------------------------------------

echo ""
echo "Starting Correspondence at http://localhost:8000"
echo "Press Ctrl+C to stop."
echo ""

# Open the browser after a short delay so the server has time to bind.
# The `open` command is macOS-specific; on Linux this falls back silently.
(sleep 1.5 && open "http://localhost:8000" 2>/dev/null) &

exec uvicorn backend.api:app --host 127.0.0.1 --port 8000 --log-level info

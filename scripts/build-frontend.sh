#!/bin/bash
# ======================================================
# QuantDinger Frontend Build Script
# Run this in your PRIVATE frontend repo to build and
# sync compiled files to the open-source repo.
#
# Usage:
#   ./scripts/build-frontend.sh
#
# Prerequisites:
#   - Node.js >= 16
#   - quantdinger_vue/ source code available
# ======================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VUE_DIR="$PROJECT_ROOT/quantdinger_vue"
DIST_TARGET="$PROJECT_ROOT/frontend/dist"

echo "============================================"
echo "  QuantDinger Frontend Build"
echo "============================================"

# Check if source exists
if [ ! -d "$VUE_DIR" ]; then
    echo "ERROR: quantdinger_vue/ directory not found!"
    echo "This script should be run in the dev environment with frontend source."
    exit 1
fi

# Build frontend
echo "[1/3] Installing dependencies..."
cd "$VUE_DIR"
npm install --legacy-peer-deps

echo "[2/3] Building production bundle..."
npm run build

# Sync dist
echo "[3/3] Syncing dist to frontend/dist/..."
rm -rf "$DIST_TARGET"/*
cp -r "$VUE_DIR/dist/"* "$DIST_TARGET/"

echo ""
echo "============================================"
echo "  Build complete!"
echo "  Output: frontend/dist/"
echo "  Files: $(find "$DIST_TARGET" -type f | wc -l)"
echo "  Size:  $(du -sh "$DIST_TARGET" | cut -f1)"
echo "============================================"
echo ""
echo "Next steps:"
echo "  cd $PROJECT_ROOT"
echo "  git add frontend/dist/"
echo "  git commit -m 'chore: update frontend build'"
echo "  git push"

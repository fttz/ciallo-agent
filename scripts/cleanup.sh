#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Cleaning runtime artifacts..."
rm -rf "$ROOT_DIR/.run" || true
rm -rf "$ROOT_DIR/apps/web/.next" || true

echo "Cleaning temporary data files..."
rm -f "$ROOT_DIR/data/sessions.json" || true

echo "Done."
echo "Removed: .run, apps/web/.next, data/sessions.json (if existed)"
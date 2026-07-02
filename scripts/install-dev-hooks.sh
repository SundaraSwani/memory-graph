#!/usr/bin/env bash
# Install git hooks for developing memory-graph itself (pre-push runs tests).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
HOOKS_DIR="$ROOT/.git/hooks"

if [ ! -d "$ROOT/.git" ]; then
  echo "No .git directory — run from inside the memory-graph repo" >&2
  exit 1
fi

chmod +x "$ROOT/scripts/test.sh" \
         "$ROOT/scripts/test-static.sh" \
         "$ROOT/scripts/test-compress-sandbox.sh" \
         "$ROOT/scripts/pre-push" \
         "$ROOT/scripts/install-dev-hooks.sh" 2>/dev/null || true

install_hook() {
  local name=$1
  local src=$2
  cp "$src" "$HOOKS_DIR/$name"
  chmod +x "$HOOKS_DIR/$name"
  echo "[ok] .git/hooks/$name"
}

install_hook pre-push "$ROOT/scripts/pre-push"

echo ""
echo "Pre-push hook installed. Tests run automatically on: git push"
echo "Manual run: bash scripts/test.sh"

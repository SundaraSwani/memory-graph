#!/usr/bin/env bash
# Cursor plugin: scaffold memory-graph into the open workspace (idempotent).
set -euo pipefail

PLUGIN_ROOT=$(cd "$(dirname "$0")/.." && pwd)
TARGET="${CURSOR_PROJECT_DIR:-${1:-$(pwd)}}"
TARGET=$(cd "$TARGET" && pwd)

if [[ ! -f "$PLUGIN_ROOT/setup" ]]; then
  echo "memory-graph plugin: setup not found at $PLUGIN_ROOT" >&2
  exit 1
fi

# Remote-mode setup copies hooks/rules/scripts into the project.
(cd "$TARGET" && bash "$PLUGIN_ROOT/setup")

# Ensure memory map exists.
if [[ ! -f "$TARGET/memory/README.md" ]] && [[ -f "$PLUGIN_ROOT/memory/README.md" ]]; then
  mkdir -p "$TARGET/memory"
  cp "$PLUGIN_ROOT/memory/README.md" "$TARGET/memory/README.md"
fi

# Seed unified config if missing.
if [[ ! -f "$TARGET/.memory-graph/config.yaml" ]] && [[ -f "$PLUGIN_ROOT/.memory-graph/config.example.yaml" ]]; then
  mkdir -p "$TARGET/.memory-graph"
  cp "$PLUGIN_ROOT/.memory-graph/config.example.yaml" "$TARGET/.memory-graph/config.yaml"
fi

echo "memory-graph: workspace ready at $TARGET"
echo '{}'

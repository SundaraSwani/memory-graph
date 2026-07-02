#!/bin/bash
# memory-graph: full graphify rebuild on git commit
# Installed to .git/hooks/post-commit by setup script.
# Re-extracts changed files (AST for code, LLM for docs/images if any).

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT"

# Resolve python interpreter
if [ -f "$REPO_ROOT/graphify-out/.graphify_python" ]; then
  PYTHON=$(cat "$REPO_ROOT/graphify-out/.graphify_python")
else
  PYTHON="python3"
fi

# Run incremental update — only re-extracts changed files
"$PYTHON" -m graphify . --update 2>/dev/null || true

# Roll up session memory → memory/state.yaml
COMPRESS="$REPO_ROOT/.cursor/hooks/compress-memory.py"
if [ -f "$COMPRESS" ]; then
  REPO_ROOT="$REPO_ROOT" python3 "$COMPRESS" 2>/dev/null || true
fi

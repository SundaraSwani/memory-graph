#!/bin/bash
# memory-graph: graphify incremental update hook
# Fires on agent stop. Runs AST-only update if code files changed (no LLM needed).
# Full rebuild happens on git post-commit via the installed git hook.

set -euo pipefail

# Consume stdin (required for all Cursor hooks)
input=$(cat)

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT"

# Skip if graphify has never been run (no python interpreter saved)
if [ ! -f "$REPO_ROOT/graphify-out/.graphify_python" ]; then
  echo '{}'
  exit 0
fi

PYTHON=$(cat "$REPO_ROOT/graphify-out/.graphify_python")

# Check for changed code files (AST-extractable — no LLM needed)
CODE_EXTS='\.(py|ts|js|tsx|jsx|go|rs|java|cpp|c|rb|swift|kt|cs|scala|php|lua)$'
CHANGED=$(git diff --name-only HEAD 2>/dev/null || true)
STAGED=$(git diff --cached --name-only 2>/dev/null || true)
CHANGED_CODE=$(printf '%s\n%s' "$CHANGED" "$STAGED" | grep -E "$CODE_EXTS" | sort -u | grep -v '^$' || true)

if [ -z "$CHANGED_CODE" ]; then
  echo '{}'
  exit 0
fi

# Run incremental AST update — fast, no LLM, safe to run on every stop
"$PYTHON" -m graphify . --update 2>/dev/null || true

echo '{}'
exit 0

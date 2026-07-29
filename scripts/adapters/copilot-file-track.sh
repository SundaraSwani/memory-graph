#!/usr/bin/env bash
# memory-graph: Copilot postToolUse file-tracking adapter
# Appends agent-edited file paths to the shared ledger (.memory-graph/changed-files)
# so on-session-end.sh sees them regardless of MEMORY_TRACK mode.
#
# Copilot postToolUse payload:
#   { sessionId, timestamp, cwd, toolName, toolArgs: { path?, filePath? }, toolResult }

set -uo pipefail

_input=$(cat)

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Only track tools that modify files
if command -v jq >/dev/null 2>&1; then
  TOOL_NAME="$(printf '%s' "$_input" | jq -r '.toolName // empty' 2>/dev/null || true)"
  # path is the primary key; filePath is a fallback for tools that use camelCase
  FILE_PATH="$(printf '%s' "$_input" | jq -r '.toolArgs.path // .toolArgs.filePath // empty' 2>/dev/null || true)"
else
  TOOL_NAME=""
  FILE_PATH=""
fi

[[ -n "$FILE_PATH" ]] || { printf '{}'; exit 0; }

# Only proceed for editing/creating tools — skip reads, searches, shell commands
case "$TOOL_NAME" in
  *edit*|*Edit*|*write*|*Write*|*create*|*Create*|*replace*|*Replace*|*insert*|*Insert*) ;;
  *) printf '{}'; exit 0 ;;
esac

# Resolve to repo-relative path
rel_path="$(
  REPO_ROOT="$REPO_ROOT" FILE_PATH="$FILE_PATH" python3 <<'PY'
import os
from pathlib import Path

repo = Path(os.environ["REPO_ROOT"]).resolve()
fp = Path(os.environ["FILE_PATH"])

if fp.is_absolute():
    try:
        rel = fp.relative_to(repo)
    except ValueError:
        raise SystemExit(0)
else:
    rel = fp

print(str(rel).replace("\\", "/"))
PY
)" || { printf '{}'; exit 0; }

[[ -n "$rel_path" ]] || { printf '{}'; exit 0; }

# Same exclusions as on-session-end._filter_internal_paths
case "$rel_path" in
  .cursor/*|sessions/*|memory.md|graphify-out/*) printf '{}'; exit 0 ;;
esac

mkdir -p "$REPO_ROOT/.memory-graph"
ledger="$REPO_ROOT/.memory-graph/changed-files"

# Dedup — only append if not already present
if [[ -f "$ledger" ]] && grep -Fxq "$rel_path" "$ledger" 2>/dev/null; then
  printf '{}'
  exit 0
fi

printf '%s\n' "$rel_path" >> "$ledger"
printf '{}'

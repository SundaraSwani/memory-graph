#!/bin/bash
# memory-graph: session capture hook
# Fires on agent stop. Creates session file + updates memory.md index.
# Only runs if git-tracked files changed this session.

set -euo pipefail

# Consume stdin (required for all Cursor hooks)
input=$(cat)

# Resolve repo root
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$REPO_ROOT"

# Get files changed since last commit (staged + unstaged)
CHANGED=$(git diff --name-only HEAD 2>/dev/null || true)
STAGED=$(git diff --cached --name-only 2>/dev/null || true)
ALL_CHANGED=$(printf '%s\n%s' "$CHANGED" "$STAGED" | sort -u | grep -v '^$' || true)

# Skip if nothing changed
if [ -z "$ALL_CHANGED" ]; then
  echo '{}'
  exit 0
fi

# Skip if only memory-graph internal files changed (sessions, memory.md, graphify-out)
NON_INTERNAL=$(echo "$ALL_CHANGED" | grep -v '^sessions/' | grep -v '^memory\.md$' | grep -v '^graphify-out/' || true)
if [ -z "$NON_INTERNAL" ]; then
  echo '{}'
  exit 0
fi

# Create sessions dir if missing
mkdir -p "$REPO_ROOT/sessions"

# Build timestamp and session filename
TIMESTAMP=$(date +"%Y-%m-%d-%H-%M")
SESSION_FILE="$REPO_ROOT/sessions/${TIMESTAMP}.md"

# Don't create duplicate if already exists for this minute
if [ -f "$SESSION_FILE" ]; then
  echo '{}'
  exit 0
fi

# Build file list (max 20 files shown)
CHANGED_COUNT=$(echo "$NON_INTERNAL" | wc -l | tr -d ' ')
CHANGED_LIST=$(echo "$NON_INTERNAL" | head -20 | tr '\n' ',' | sed 's/,$//')

# Write session file header — AI fills ## Decisions below
cat > "$SESSION_FILE" <<SESSIONEOF
---
date: $(date +"%Y-%m-%d %H:%M")
files_changed: $CHANGED_COUNT
files: [$CHANGED_LIST]
god_nodes_touched: []
---

<!-- memory-graph: append ## Decisions below with caveman-style "why" bullets (3-5 max) -->
SESSIONEOF

# Initialize memory.md if missing
if [ ! -f "$REPO_ROOT/memory.md" ]; then
  cat > "$REPO_ROOT/memory.md" <<'MEMEOF'
# Session Memory Index

> Auto-maintained by memory-graph.

| Date | Files Changed | Session |
|------|--------------|---------|
MEMEOF
fi

# Append new row to memory.md index
echo "| $(date +"%Y-%m-%d %H:%M") | $CHANGED_COUNT | [${TIMESTAMP}](sessions/${TIMESTAMP}.md) |" >> "$REPO_ROOT/memory.md"

# Ask agent to write decisions to the session file
SESSION_REL="sessions/${TIMESTAMP}.md"
echo "{\"followup_message\": \"Session recorded at \`${SESSION_REL}\`. Before you finish, add a \`## Decisions\` section to that file — caveman style. What was decided, what was deferred, which god nodes were touched. 3-5 bullets max.\"}"
exit 0

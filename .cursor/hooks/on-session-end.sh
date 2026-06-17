#!/usr/bin/env bash
# memory-graph: on-session-end hook
# Fires at the end of every Cursor agent stop event.
# Does three things:
#   1. Creates a session file in sessions/ with frontmatter (changed files)
#   2. Appends a row to memory.md index
#   3. Runs graphify --update in background if code files changed (AST-only, no LLM)
#   4. Returns a followup_message asking the agent to write its Decisions

set -euo pipefail

_input=$(cat)

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# ── 1. Detect changed files (staged + unstaged, excluding internal files) ──
raw_changed=$(
  { git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; } \
  | sort -u \
  | grep -v '^sessions/' \
  | grep -v '^memory\.md$' \
  | grep -v '^graphify-out/' \
  | grep -v '^$' \
  || true
)

if [ -z "$raw_changed" ]; then
  echo '{}'
  exit 0
fi

# ── 2. Build session file path (YYYY-MM-DD-N.md — N resets each day) ───────
today=$(date +%Y-%m-%d)
mkdir -p "$REPO_ROOT/sessions"
existing=$(ls "$REPO_ROOT/sessions/${today}"-*.md 2>/dev/null | wc -l | tr -d ' ')
session_num=$((existing + 1))
session_file="sessions/${today}-${session_num}.md"

# Skip if this session file already exists and has decisions written
if [ -f "$REPO_ROOT/$session_file" ]; then
  has_decisions=$(grep -c "^-" "$REPO_ROOT/$session_file" 2>/dev/null || echo 0)
  if [ "$has_decisions" -gt 0 ]; then
    echo '{}'
    exit 0
  fi
fi

# ── 3. Detect code file changes (for graphify AST update) ──────────────────
code_exts='\.py$|\.ts$|\.tsx$|\.js$|\.jsx$|\.go$|\.rs$|\.java$|\.cpp$|\.c$|\.rb$|\.swift$|\.kt$|\.cs$|\.scala$|\.php$'
has_code=$(echo "$raw_changed" | grep -E "$code_exts" | head -1 || true)

# ── 4. Write session file header ───────────────────────────────────────────
file_count=$(echo "$raw_changed" | wc -l | tr -d ' ')
files_yaml=$(echo "$raw_changed" | awk '{print "  - " $0}')

cat > "$REPO_ROOT/$session_file" <<TEMPLATE
---
date: ${today}
session: ${session_num}
files_changed: ${file_count}
files:
${files_yaml}
god_nodes_touched: []
---

## Decisions

<!-- Append caveman-style bullets here: terse "why", not "what". 3-5 max.
     Example:
     - JWT not sessions. Stateless app.
     - auth.ts now god node. Everything touches it.
     - Refresh token deferred. Ship first.
-->
TEMPLATE

# ── 5. Append row to memory.md ─────────────────────────────────────────────
new_row="| ${today} | ${session_num} | ${file_count} | [view](${session_file}) |"

if ! grep -q "| Date | Session |" "$REPO_ROOT/memory.md" 2>/dev/null; then
  # memory.md missing the table header — rewrite it
  cat > "$REPO_ROOT/memory.md" <<MEMEOF
# Session Memory Index

> Auto-maintained by memory-graph. Do not edit manually.
> Full session files live in \`sessions/\`. This file is the index.

| Date | Session | Files Changed | Session File |
|------|---------|--------------|--------------|
${new_row}
MEMEOF
else
  echo "$new_row" >> "$REPO_ROOT/memory.md"
fi

# ── 6. Graphify incremental update (background, AST-only, no LLM) ──────────
if [ -n "$has_code" ] && [ -f "$REPO_ROOT/graphify-out/.graphify_python" ]; then
  PYTHON=$(cat "$REPO_ROOT/graphify-out/.graphify_python")
  ("$PYTHON" -m graphify . --update > /dev/null 2>&1) &
fi

# ── 7. gstack context-save (if available) ─────────────────────────────────
if command -v gstack-context-save >/dev/null 2>&1; then
  (gstack-context-save > /dev/null 2>&1) &
fi

# ── 8. Ask agent to fill in Decisions ─────────────────────────────────────
cat <<JSON
{"followup_message": "Session file created at \`${session_file}\`. Before finishing: (1) append a ## Decisions section with 3-5 caveman-style bullets — the *why*, anything deferred, any god nodes touched; (2) if you used a gstack skill this session, run \`/learn\` to persist key learnings. Keep it terse."}
JSON
exit 0

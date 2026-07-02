#!/usr/bin/env bash
# Sandbox test for compress-memory.py + hook gates. No network, no LLM.
set -euo pipefail

unset MEMORY_COMPRESS_VERBOSE MEMORY_OPEN_MAX MEMORY_ARCHIVE_DAYS REPO_ROOT

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SANDBOX=$(mktemp -d /tmp/memory-graph-test-XXXXXX)
HOOK_DIR=""
HOOK2=""
HOOK3=""
trap 'rm -rf "$SANDBOX" "$HOOK_DIR" "$HOOK2" "$HOOK3"' EXIT

count_files() { { find "$1" -name "$2" 2>/dev/null; true; } | wc -l | tr -d ' '; }

assert() {
  [[ "$1" == "$2" ]] || { echo "FAIL: $3 (got '$1', want '$2')"; exit 1; }
}

mkdir -p "$SANDBOX/sessions" "$SANDBOX/.cursor/hooks"
cp "$ROOT/.cursor/hooks/compress-memory.py" "$SANDBOX/.cursor/hooks/"

cat > "$SANDBOX/sessions/2026-06-01-1.md" <<'EOF'
---
date: 2026-06-01
session: 1
open:
  - "old task"
blocked: []
context: ""
god_nodes_touched: []
---

## Decisions
- Archived legacy note.
EOF

cat > "$SANDBOX/sessions/2026-07-01-1.md" <<'EOF'
---
date: 2026-07-01
session: 1
open:
  - "active task"
blocked: []
context: "recent work"
god_nodes_touched: []
---
EOF

cat > "$SANDBOX/memory.md" <<'EOF'
# Session Memory Index
| Date/Time | Session | Topics | Files | Session File |
|-----------|---------|--------|-------|--------------|
EOF
for i in $(seq 1 35); do
  echo "| 2026-05-01 10:00 | $i | t | 1 | [v](s) |" >> "$SANDBOX/memory.md"
done

REPO_ROOT="$SANDBOX" python3 "$SANDBOX/.cursor/hooks/compress-memory.py" >/dev/null

assert "$(count_files "$SANDBOX/sessions" '*.md')" "1" "one active session"
assert "$(count_files "$SANDBOX/sessions/archive" '*.yaml')" "1" "one archive month"
assert "$(grep -c '^| 2026' "$SANDBOX/memory.md")" "30" "index trimmed to 30"
grep -q "active task" "$SANDBOX/memory/state.yaml" || { echo "FAIL: state missing open item"; exit 1; }
grep -q "recent work" "$SANDBOX/memory/state.yaml" || { echo "FAIL: state missing context"; exit 1; }
grep -q "Archived legacy note" "$SANDBOX/sessions/archive/2026-06.yaml" || { echo "FAIL: archive missing full body"; exit 1; }

REPO_ROOT="$SANDBOX" python3 "$SANDBOX/.cursor/hooks/compress-memory.py" >/dev/null
assert "$(count_files "$SANDBOX/sessions" '*.md')" "1" "idempotent active count"

# Hook: .cursor-only change → no session
HOOK_DIR=$(mktemp -d /tmp/memory-graph-hook-XXXXXX)
cp -R "$ROOT/.cursor" "$HOOK_DIR/"
cp "$ROOT/memory.md" "$HOOK_DIR/"
mkdir -p "$HOOK_DIR/src"
cd "$HOOK_DIR"
git init -q
git config user.email "test@test.com"
git config user.name "Test"
echo "ok" > src/a.go
git add . && git commit -q -m "init"
echo "# tweak" >> .cursor/rules/main.mdc
out=$(printf '{"loop_count":0,"status":"completed"}\n' | bash .cursor/hooks/on-session-end.sh)
assert "$out" "{}" "hook returns empty JSON"
assert "$(count_files "$HOOK_DIR/sessions" '*.md')" "0" ".cursor-only change skips session"

# Hook: 3 files → session + state (fresh repo — no .cursor noise)
HOOK3=$(mktemp -d /tmp/memory-graph-hook3-XXXXXX)
cp -R "$ROOT/.cursor" "$HOOK3/"
cp "$ROOT/memory.md" "$HOOK3/"
mkdir -p "$HOOK3/src"
cd "$HOOK3"
git init -q && git config user.email "t@t.com" && git config user.name "T"
echo "ok" > src/a.go && git add . && git commit -q -m "init"
echo "a" >> src/a.go
echo "b" > src/b.go
echo "c" > src/c.go
git add src/
printf '{"loop_count":0,"status":"completed"}\n' | bash .cursor/hooks/on-session-end.sh >/dev/null
sleep 1
assert "$(count_files "$HOOK3/sessions" '*.md')" "1" "3-file change creates session"
test -f "$HOOK3/memory/state.yaml" || { echo "FAIL: hook did not produce state.yaml"; exit 1; }

# Hook: 1 file → skipped
HOOK2=$(mktemp -d /tmp/memory-graph-hook2-XXXXXX)
cp -R "$ROOT/.cursor" "$HOOK2/"
cp "$ROOT/memory.md" "$HOOK2/"
mkdir -p "$HOOK2/src"
cd "$HOOK2"
git init -q && git config user.email "t@t.com" && git config user.name "T"
echo "x" > src/a.go && git add . && git commit -q -m "init"
echo "y" >> src/a.go
printf '{"loop_count":0,"status":"completed"}\n' | bash .cursor/hooks/on-session-end.sh >/dev/null
assert "$(count_files "$HOOK2/sessions" '*.md')" "0" "single-file change skipped"

echo "OK — all sandbox assertions passed"

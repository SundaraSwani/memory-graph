#!/usr/bin/env bash
# Sandbox test for compress-memory.py + hook gates. No network, no LLM.
set -euo pipefail

unset MEMORY_COMPRESS_VERBOSE MEMORY_OPEN_MAX MEMORY_ARCHIVE_DAYS REPO_ROOT

ROOT=$(cd "$(dirname "$0")/.." && pwd)
TODAY=$(date +%Y-%m-%d)
SANDBOX=$(mktemp -d /tmp/memory-graph-test-XXXXXX)
HOOK_DIR=""
HOOK2=""
HOOK3=""
HOOK4=""
HOOK5=""
trap 'rm -rf "$SANDBOX" "$HOOK_DIR" "$HOOK2" "$HOOK3" "$HOOK4" "$HOOK5"' EXIT

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

cat > "$SANDBOX/sessions/${TODAY}-1.md" <<EOF
---
date: ${TODAY}
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

# Hook: 1 file → no new session, but compress still refreshes state.yaml
HOOK2=$(mktemp -d /tmp/memory-graph-hook2-XXXXXX)
cp -R "$ROOT/.cursor" "$HOOK2/"
cp "$ROOT/memory.md" "$HOOK2/"
mkdir -p "$HOOK2/src" "$HOOK2/sessions" "$HOOK2/memory"
cat > "$HOOK2/sessions/2026-06-01-1.md" <<'EOF'
---
date: 2026-06-01
session: 1
open:
  - "seed task from prior session"
blocked: []
context: "carry forward"
god_nodes_touched: []
---
EOF
cd "$HOOK2"
git init -q && git config user.email "t@t.com" && git config user.name "T"
echo "x" > src/a.go && git add . && git commit -q -m "init"
echo "y" >> src/a.go
printf '{"loop_count":0,"status":"completed"}\n' | bash .cursor/hooks/on-session-end.sh >/dev/null
sleep 1
assert "$(count_files "$HOOK2/sessions" '*.md')" "0" "single-file change skipped (no new session today)"
grep -q "seed task from prior session" "$HOOK2/memory/state.yaml" || \
  { echo "FAIL: low-signal stop did not compress existing sessions"; exit 1; }

# Hook: no git, MEMORY_TRACK=cursor — ledger drives session creation
HOOK4=$(mktemp -d /tmp/memory-graph-hook4-XXXXXX)
cp -R "$ROOT/.cursor" "$HOOK4/"
cp "$ROOT/memory.md" "$HOOK4/"
mkdir -p "$HOOK4/src" "$HOOK4/.memory-graph"
cd "$HOOK4"
printf 'src/a.go\nsrc/b.go\nsrc/c.go\n' > .memory-graph/changed-files
MEMORY_TRACK=cursor printf '{"loop_count":0,"status":"completed"}\n' | bash .cursor/hooks/on-session-end.sh >/dev/null
sleep 1
assert "$(count_files "$HOOK4/sessions" '*.md')" "1" "cursor ledger creates session without git"
test ! -f "$HOOK4/.memory-graph/changed-files" || { echo "FAIL: ledger not cleared after stop"; exit 1; }

# afterFileEdit tracker: records path, skips internal .cursor edits
HOOK5=$(mktemp -d /tmp/memory-graph-hook5-XXXXXX)
cp -R "$ROOT/.cursor" "$HOOK5/"
mkdir -p "$HOOK5/src"
cd "$HOOK5"
printf '{"file_path":"src/a.go","workspace_roots":["%s"],"hook_event_name":"afterFileEdit"}\n' "$HOOK5" \
  | bash .cursor/hooks/track-changed-files.sh
grep -Fxq 'src/a.go' .memory-graph/changed-files || { echo "FAIL: tracker did not record src/a.go"; exit 1; }
printf '{"file_path":".cursor/rules/main.mdc","workspace_roots":["%s"]}\n' "$HOOK5" \
  | bash .cursor/hooks/track-changed-files.sh
assert "$(wc -l < .memory-graph/changed-files | tr -d ' ')" "1" "tracker skips .cursor paths"

# auto mode: cursor ledger wins over noisy git diff (bulk deletions ignored)
HOOK6=$(mktemp -d /tmp/memory-graph-hook6-XXXXXX)
cp -R "$ROOT/.cursor" "$HOOK6/"
cp "$ROOT/memory.md" "$HOOK6/"
mkdir -p "$HOOK6/src/tests" "$HOOK6/.memory-graph"
cd "$HOOK6"
git init -q && git config user.email "t@t.com" && git config user.name "T"
echo "ok" > src/a.go && git add . && git commit -q -m "init"
# Simulate bulk delete noise in working tree
for i in $(seq 1 30); do echo "x" > "deleted_${i}.txt"; git add "deleted_${i}.txt"; done
git commit -q -m "add noise"
rm deleted_*.txt
# Agent actually edited these three files this session
printf 'src/tests/fixture_a.py\nsrc/tests/fixture_b.py\nsrc/tests/test_html.py\n' > .memory-graph/changed-files
printf '{"loop_count":0,"status":"completed"}\n' | bash .cursor/hooks/on-session-end.sh >/dev/null
sleep 1
session=$(ls "$HOOK6/sessions"/*.md 2>/dev/null | head -1)
grep -q 'src/tests/fixture_a.py' "$session" || { echo "FAIL: auto mode should prefer cursor ledger over git noise"; exit 1; }
grep -q 'deleted_1.txt' "$session" && { echo "FAIL: auto mode must not include bulk deletions when ledger present"; exit 1; }

# fill-session-from-transcript: rules-based context
TRANSCRIPT=$(mktemp /tmp/mg-transcript-XXXXXX.jsonl)
cat > "$TRANSCRIPT" <<'EOF'
{"role":"user","message":{"content":[{"type":"text","text":"<user_query>Fix discount HTML pytest fixtures</user_query>"}]}}
{"role":"assistant","message":{"content":[{"type":"text","text":"Updated three discount fixture cases. Still need to fix the remaining failing assertions in test_html.py."}]}}
EOF
TEST_SESSION=$(mktemp /tmp/mg-session-XXXXXX.md)
cat > "$TEST_SESSION" <<'EOF'
---
date: 2026-07-06
time: 12:00
session: 1
topics: "tests"
scope:
  - src/tests/test_html.py
god_nodes_touched:
  []
open: []
blocked: []
context: ""
facts: []
---
EOF
REPO_ROOT="$HOOK6" python3 "$HOOK6/.cursor/hooks/fill-session-from-transcript.py" "$TEST_SESSION" "$TRANSCRIPT"
grep -q '^context: "Updated three discount' "$TEST_SESSION" || { echo "FAIL: fill script did not write context"; exit 1; }
grep -q 'test_html.py' "$TEST_SESSION" || { echo "FAIL: fill script should capture open items"; exit 1; }
rm -f "$TRANSCRIPT" "$TEST_SESSION"

# sessionStart: token-first injects cursor-context when enabled
GATEWAY=$(mktemp -d /tmp/memory-graph-gateway-XXXXXX)
cp -R "$ROOT/.cursor" "$GATEWAY/"
mkdir -p "$GATEWAY/memory" "$GATEWAY/.memory-graph"
cat > "$GATEWAY/.memory-graph/config.yaml" <<'EOF'
agent_brief: true
ollama_context_on_start: true
EOF
cat > "$GATEWAY/memory/.cursor-context.yaml" <<'EOF'
# Auto-generated by ollama-context-gateway.py
updated: 2026-07-06
open:
  - "gateway test task"
recent:
  - "slim context for session start"
EOF
cd "$GATEWAY"
out=$(bash .cursor/hooks/on-session-start.sh)
echo "$out" | grep -q 'slim context for session start' || { echo "FAIL: sessionStart must inject cursor-context"; exit 1; }
echo "$out" | grep -q 'slim context below' || { echo "FAIL: token-first preamble missing"; exit 1; }
echo "$out" | grep -q '## Graph scout' && { echo "FAIL: sessionStart must not inject graph scout section"; exit 1; }

# gateway --dry-run gathers source without network
GW2=$(mktemp -d /tmp/memory-graph-gw2-XXXXXX)
cp "$ROOT/.cursor/hooks/ollama-context-gateway.py" "$GW2/"
cp "$ROOT/.cursor/hooks/semantic-compress-ollama.py" "$GW2/"
mkdir -p "$GW2/memory" "$GW2/sessions" "$GW2/.memory-graph"
cat > "$GW2/.memory-graph/config.yaml" <<'EOF'
ollama_context_on_start: true
EOF
cat > "$GW2/memory/state.yaml" <<'EOF'
updated: 2026-07-06
open:
  - "dry run seed"
recent_context:
  - "seed context line"
EOF
REPO_ROOT="$GW2" python3 "$GW2/ollama-context-gateway.py" --dry-run | grep -q 'dry run seed' || \
  { echo "FAIL: gateway dry-run must include state.yaml source"; exit 1; }

echo "OK — all sandbox assertions passed"

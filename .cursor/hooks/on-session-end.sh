#!/usr/bin/env bash
# memory-graph: on-session-end hook
# Fires at the end of every Cursor agent stop event.
# Only runs when git-tracked files changed — pure Q&A sessions produce no session file.
#
# What it does:
#   1. Guards against loops (only fires once per chat, only on clean completion)
#   2. Detects changed files via git diff (staged + unstaged), excluding internal paths
#   3. Skips low-signal changes (<3 files and no god-node blast radius)
#   4. Creates sessions/YYYY-MM-DD-N.md with structured YAML frontmatter (no prose template)
#   5. Appends a row to memory.md index
#   6. Runs graphify --update in background if code files changed (AST-only, no LLM)
#   7. Syncs god nodes into main.mdc from the refreshed graph
#   8. Compresses memory → memory/state.yaml on every file-changing stop (daily archive)
#   9. Optionally triggers semantic-compress via followup when auto enabled + caps hit
#  10. Exits silently — no followup unless semantic auto (avoids extra turns otherwise)

set -uo pipefail

_input=$(cat)

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

_semantic_sync_needed() {
  [[ "${MEMORY_SEMANTIC_AUTO:-}" == "1" ]] && return 0
  [[ -f "$REPO_ROOT/.memory-graph-semantic-auto" ]] && return 0
  [[ -f "$REPO_ROOT/.memory-graph/ollama.yaml" ]] && \
    grep -qE '^enabled:[[:space:]]*true' "$REPO_ROOT/.memory-graph/ollama.yaml" 2>/dev/null && return 0
  return 1
}

_run_memory_compress() {
  local script="$REPO_ROOT/.cursor/hooks/compress-memory.py"
  [[ -f "$script" ]] || return 0
  if _semantic_sync_needed; then
    REPO_ROOT="$REPO_ROOT" python3 "$script" >/dev/null 2>&1 || true
  else
    ( REPO_ROOT="$REPO_ROOT" python3 "$script" > /dev/null 2>&1 ) &
  fi
}

_maybe_semantic_ollama() {
  local cfg="$REPO_ROOT/.memory-graph/ollama.yaml"
  local ollama_py="$REPO_ROOT/.cursor/hooks/semantic-compress-ollama.py"
  [[ -f "$cfg" && -f "$ollama_py" ]] || return 1
  grep -qE '^enabled:[[:space:]]*true' "$cfg" 2>/dev/null || return 1
  [[ -f "$REPO_ROOT/memory/.semantic-pending" ]] || return 1
  if REPO_ROOT="$REPO_ROOT" python3 "$ollama_py" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

_maybe_semantic_followup() {
  # Skip agent followup if Ollama handled compression this stop
  [[ -f "$REPO_ROOT/memory/.semantic-pending" ]] || return 1
  [[ "${MEMORY_SEMANTIC_AUTO:-}" == "1" || -f "$REPO_ROOT/.memory-graph-semantic-auto" ]] || return 1

  local pending="$REPO_ROOT/memory/.semantic-pending"
  [[ -f "$pending" ]] || return 1

  local reasons
  reasons=$(grep '^  - ' "$pending" 2>/dev/null | head -3 | tr '\n' ' ' | sed 's/  - //g')

  cat <<JSON
{"followup_message": "Structural memory is full (${reasons}). Run the semantic-compress skill: distill \`memory/state.yaml\` + \`sessions/archive/\` into ≤15 lines in \`memory/state.yaml\`, drop resolved \`open\` items, then delete \`memory/.semantic-pending\` and write today's date to \`memory/.semantic-last-run\`. One pass only."}
JSON
  exit 0
}

_finish() {
  _run_memory_compress
  if _maybe_semantic_ollama; then
    printf '{}'
    exit 0
  fi
  _maybe_semantic_followup
  printf '{}'
  exit 0
}

# ── 1. Loop guard — only fire once per chat, only on clean completion ───────
if command -v jq >/dev/null 2>&1; then
  LOOP_COUNT="$(printf '%s' "$_input" | jq -r '.loop_count // 0' 2>/dev/null || echo 0)"
  STATUS="$(printf '%s' "$_input" | jq -r '.status // "completed"' 2>/dev/null || echo completed)"
  if [[ "$LOOP_COUNT" -ge 1 || "$STATUS" != "completed" ]]; then
    printf '{}'
    exit 0
  fi
fi

# ── 2. Detect changed files (staged + unstaged, excluding internal files) ───
raw_changed=$(
  { git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null; } \
  | sort -u \
  | grep -v '^\.cursor/' \
  | grep -v '^sessions/' \
  | grep -v '^memory\.md$' \
  | grep -v '^graphify-out/' \
  | grep -v '^$' \
  || true
)

if [ -z "$raw_changed" ]; then
  printf '{}'
  exit 0
fi

file_count=$(echo "$raw_changed" | wc -l | tr -d ' ')

# ── 3. Graph impact (for god-node gating + session prefill) ───────────────────
god_nodes_hit=""
graph_facts=""
export CHANGED_FILES="$raw_changed"
if [ -f "$REPO_ROOT/graphify-out/graph.json" ] && command -v python3 >/dev/null 2>&1; then
  eval "$(python3 - "$REPO_ROOT/graphify-out/graph.json" <<'PYEOF'
import json, sys, os, shlex
from collections import defaultdict, Counter

graph_file = sys.argv[1]
changed_files = [f.strip() for f in os.environ.get("CHANGED_FILES", "").splitlines() if f.strip()]

god_nodes_hit = []
facts = []

try:
    g = json.loads(open(graph_file).read())
    nodes = g.get("nodes", [])
    links = g.get("links", g.get("edges", []))

    degree = Counter()
    for e in links:
        degree[e.get("source", "")] += 1
        degree[e.get("target", "")] += 1

    def risk(d):
        if d >= 200: return "CRITICAL"
        if d >= 100: return "HIGH"
        if d >= 60:  return "MEDIUM"
        return "LOW"

    touched_communities = defaultdict(list)
    for node in nodes:
        nid = node.get("id", "")
        for cf in changed_files:
            if cf in nid or nid in cf:
                comm = node.get("community", node.get("group", "?"))
                label = node.get("label", nid)
                touched_communities[comm].append(label)
                r = risk(degree.get(nid, 0))
                if r in ("CRITICAL", "HIGH"):
                    god_nodes_hit.append(f"{label} ({r})")
                break

    for comm, labels in list(touched_communities.items())[:4]:
        sample = ", ".join(labels[:3])
        if len(labels) > 3:
            sample += f" (+{len(labels)-3} more)"
        facts.append(f"community {comm}: {sample}")

    if god_nodes_hit:
        facts.insert(0, f"god nodes in blast radius: {', '.join(god_nodes_hit[:5])}")

except Exception:
    pass

def emit(name, value):
    if value:
        print(f"{name}={shlex.quote(value)}")

emit("GOD_NODES_HIT", ", ".join(god_nodes_hit))
emit("GRAPH_FACTS", "\\n".join(f"- {f}" for f in facts))
PYEOF
  )" 2>/dev/null || true
fi

# ── 4. Smart gate — skip low-signal sessions (<3 files, no god-node hit) ────
if [ "$file_count" -lt 3 ] && [ -z "$god_nodes_hit" ]; then
  # Still run graphify AST update in background if code changed, but no session file
  code_exts='\.py$|\.ts$|\.tsx$|\.js$|\.jsx$|\.go$|\.rs$|\.java$|\.cpp$|\.c$|\.rb$|\.swift$|\.kt$|\.cs$|\.scala$|\.php$'
  has_code=$(echo "$raw_changed" | grep -E "$code_exts" | head -1 || true)
  if [ -n "$has_code" ] && [ -f "$REPO_ROOT/graphify-out/.graphify_python" ]; then
    PYTHON=$(cat "$REPO_ROOT/graphify-out/.graphify_python")
    ( "$PYTHON" -m graphify update . > /dev/null 2>&1 ) &
  fi
  _finish
fi

# ── 5. Build session file path (YYYY-MM-DD-N.md — N resets each day) ────────
today=$(date +%Y-%m-%d)
now=$(date +%H:%M)
mkdir -p "$REPO_ROOT/sessions"
existing=0
existing=$(ls "$REPO_ROOT/sessions/${today}"-*.md 2>/dev/null | wc -l | tr -d ' ') || existing=0
session_num=$((existing + 1))
session_file="sessions/${today}-${session_num}.md"

# Skip if session already has context filled
if [ -f "$REPO_ROOT/$session_file" ]; then
  has_context=$(grep -E '^context: ".+"' "$REPO_ROOT/$session_file" 2>/dev/null | wc -l | tr -d ' ') || has_context=0
  if [ "$has_context" -gt 0 ]; then
    _finish
  fi
fi

# ── 6. Derive topic hints ────────────────────────────────────────────────────
topics=$(echo "$raw_changed" | awk -F'/' '
  {
    if (NF >= 3) label = $2 "/" $3
    else if (NF == 2) label = $2
    else label = $1
    seen[label] = 1
  }
  END {
    n = 0
    for (k in seen) { keys[n++] = k }
    out = ""
    for (i = 0; i < n && i < 5; i++) {
      out = (out == "") ? keys[i] : out ", " keys[i]
    }
    print out
  }
' || true)

files_yaml=$(echo "$raw_changed" | awk '{print "  - " $0}')

# God nodes YAML list
god_nodes_yaml="  []"
if [ -n "$god_nodes_hit" ]; then
  god_nodes_yaml=$(echo "$god_nodes_hit" | awk -F', ' '{print "  - " $1}' | head -5)
fi

facts_block=""
if [ -n "$graph_facts" ]; then
  facts_block="facts:
$(echo "$graph_facts" | sed 's/^/  /')"
else
  facts_block="facts: []"
fi

# ── 7. Write structured session file (frontmatter only — no prose sections) ─
cat > "$REPO_ROOT/$session_file" <<TEMPLATE
---
date: ${today}
time: ${now}
session: ${session_num}
topics: "${topics}"
scope:
${files_yaml}
god_nodes_touched:
${god_nodes_yaml}
open: []
blocked: []
context: ""
${facts_block}
---
TEMPLATE

# ── 8. Append row to memory.md ──────────────────────────────────────────────
new_row="| ${today} ${now} | ${session_num} | ${topics} | ${file_count} files | [view](${session_file}) |"

if ! grep -q "| Date/Time |" "$REPO_ROOT/memory.md" 2>/dev/null; then
  cat > "$REPO_ROOT/memory.md" <<MEMEOF
# Session Memory Index

> Auto-maintained by memory-graph. Structured context lives in \`sessions/\` frontmatter.

| Date/Time | Session | Topics | Files | Session File |
|-----------|---------|--------|-------|--------------|
${new_row}
MEMEOF
else
  echo "$new_row" >> "$REPO_ROOT/memory.md"
fi

# ── 9. Graphify incremental update + main.mdc god-node sync ─────────────────
code_exts='\.py$|\.ts$|\.tsx$|\.js$|\.jsx$|\.go$|\.rs$|\.java$|\.cpp$|\.c$|\.rb$|\.swift$|\.kt$|\.cs$|\.scala$|\.php$'
has_code=$(echo "$raw_changed" | grep -E "$code_exts" | head -1 || true)

if [ -n "$has_code" ] && [ -f "$REPO_ROOT/graphify-out/.graphify_python" ]; then
  PYTHON=$(cat "$REPO_ROOT/graphify-out/.graphify_python")
  (
    "$PYTHON" -m graphify update . > /dev/null 2>&1

    MAIN_MDC="$REPO_ROOT/.cursor/rules/main.mdc"
    GRAPH_JSON="$REPO_ROOT/graphify-out/graph.json"
    if [ -f "$MAIN_MDC" ] && [ -f "$GRAPH_JSON" ]; then
      MAIN_MDC="$MAIN_MDC" GRAPH_JSON="$GRAPH_JSON" "$PYTHON" - <<'PYEOF'
import json, re, os
from pathlib import Path
from collections import Counter

mdc_path = Path(os.environ["MAIN_MDC"])
graph_path = Path(os.environ["GRAPH_JSON"])

try:
    g = json.loads(graph_path.read_text())
    nodes = g.get("nodes", [])
    links = g.get("links", g.get("edges", []))

    degree = Counter()
    for e in links:
        degree[e.get("source", "")] += 1
        degree[e.get("target", "")] += 1

    node_by_id = {n["id"]: n for n in nodes}
    top10 = sorted(degree.items(), key=lambda x: -x[1])[:10]

    def risk(d):
        if d >= 200: return "CRITICAL"
        if d >= 100: return "HIGH"
        if d >= 60:  return "MEDIUM"
        return "LOW"

    rows = ["| # | Node | Edges | Risk |", "|---|------|-------|------|"]
    for i, (nid, deg) in enumerate(top10, 1):
        label = node_by_id.get(nid, {}).get("label", nid)
        rows.append(f"| {i} | `{label}` | {deg} | {risk(deg)} |")
    god_table = "\n".join(rows)

    ts = __import__("datetime").date.today().isoformat()
    mdc = mdc_path.read_text()

    mdc = re.sub(
        r"(<!-- Last updated: )[^-\n]+",
        f"\\g<1>{ts}",
        mdc,
        count=1,
    )

    mdc = re.sub(
        r"(<!-- Last updated: [^\n]+ -->)\n\n(?:[^\n#].*?\n\n)?(> Before editing|_No graph yet)",
        f"\\g<1>\n\n{god_table}\n\n\\g<2>",
        mdc,
        flags=re.DOTALL,
        count=1,
    )

    if "_No graph yet" not in mdc and "> Before editing" not in mdc:
        mdc = re.sub(
            r"(## God Nodes\n\n<!-- Auto-updated by graphify[^\n]* -->\n<!-- Last updated: [^\n]+ -->)\n\n.*?(?=\n\n> Before editing|\n\n---|\n\n## |\Z)",
            f"\\g<1>\n\n{god_table}",
            mdc,
            flags=re.DOTALL,
            count=1,
        )

    mdc_path.write_text(mdc)
except Exception as e:
    import sys
    print(f"graphify main.mdc sync error: {e}", file=sys.stderr)
PYEOF
    fi
  ) &
fi

# ── 10. Optional gstack context-save (no followup) ───────────────────────────
if command -v gstack-context-save >/dev/null 2>&1; then
  (gstack-context-save > /dev/null 2>&1 ) &
fi

_finish

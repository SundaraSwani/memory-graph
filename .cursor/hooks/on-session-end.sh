#!/usr/bin/env bash
# memory-graph: on-session-end hook
# Fires at the end of every Cursor agent stop event.
# Only runs when git-tracked files changed — pure Q&A sessions produce no session file.
#
# What it does:
#   1. Guards against loops (only fires once per chat, only on clean completion)
#   2. Detects changed files via git diff (staged + unstaged)
#   3. Creates sessions/YYYY-MM-DD-N.md with frontmatter + three-section template
#   4. Appends a row to memory.md index
#   5. Runs graphify --update in background if code files changed (AST-only, no LLM)
#   6. Syncs god nodes + stats into main.mdc from the refreshed graph
#   7. Returns a followup_message asking the agent to fill in its decisions

set -uo pipefail

_input=$(cat)

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

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
  | grep -v '^sessions/' \
  | grep -v '^memory\.md$' \
  | grep -v '^graphify-out/' \
  | grep -v '^$' \
  || true
)

# Exit silently if nothing changed — pure Q&A sessions don't get session files
if [ -z "$raw_changed" ]; then
  printf '{}'
  exit 0
fi

# ── 3. Build session file path (YYYY-MM-DD-N.md — N resets each day) ────────
today=$(date +%Y-%m-%d)
now=$(date +%H:%M)
mkdir -p "$REPO_ROOT/sessions"
existing=0
existing=$(ls "$REPO_ROOT/sessions/${today}"-*.md 2>/dev/null | wc -l | tr -d ' ') || existing=0
session_num=$((existing + 1))
session_file="sessions/${today}-${session_num}.md"

# Skip if this session file already exists and has decisions written.
# Use "^- " (dash + space) to match bullet points only — avoids matching YAML "---" delimiters.
if [ -f "$REPO_ROOT/$session_file" ]; then
  has_decisions=$(grep -c "^- " "$REPO_ROOT/$session_file" 2>/dev/null || echo 0)
  if [ "$has_decisions" -gt 0 ]; then
    printf '{}'
    exit 0
  fi
fi

# ── 4. Detect code file changes (for graphify AST update) ───────────────────
code_exts='\.py$|\.ts$|\.tsx$|\.js$|\.jsx$|\.go$|\.rs$|\.java$|\.cpp$|\.c$|\.rb$|\.swift$|\.kt$|\.cs$|\.scala$|\.php$'
has_code=$(echo "$raw_changed" | grep -E "$code_exts" | head -1 || true)

# ── 5. Derive topic hints from changed file paths ────────────────────────────
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

# ── 6. Write session file ────────────────────────────────────────────────────
file_count=$(echo "$raw_changed" | wc -l | tr -d ' ')
files_yaml=$(echo "$raw_changed" | awk '{print "  - " $0}')

cat > "$REPO_ROOT/$session_file" <<TEMPLATE
---
date: ${today}
time: ${now}
session: ${session_num}
topics: "${topics}"
files_changed: ${file_count}
files:
${files_yaml}
god_nodes_touched: []
---

## What happened

<!-- 1-2 sentences: what was the task / what changed -->

## Decisions

<!-- Why, not what. 3-5 caveman bullets.
     - JWT not sessions. Stateless.
     - Deferred refresh token. Ship first.
-->

## What to pick up next

<!-- Unfinished threads, follow-ups, open questions -->
TEMPLATE

# ── 7. Append row to memory.md ──────────────────────────────────────────────
new_row="| ${today} ${now} | ${session_num} | ${topics} | ${file_count} files | [view](${session_file}) |"

if ! grep -q "| Date/Time |" "$REPO_ROOT/memory.md" 2>/dev/null; then
  cat > "$REPO_ROOT/memory.md" <<MEMEOF
# Session Memory Index

> Auto-maintained by memory-graph. Do not edit manually.
> Full session files live in \`sessions/\`. This file is the index.

| Date/Time | Session | Topics | Files | Session File |
|-----------|---------|--------|-------|--------------|
${new_row}
MEMEOF
else
  echo "$new_row" >> "$REPO_ROOT/memory.md"
fi

# ── 8. Graphify incremental update + main.mdc sync ───────────────────────────
if [ -n "$has_code" ] && [ -f "$REPO_ROOT/graphify-out/.graphify_python" ]; then
  PYTHON=$(cat "$REPO_ROOT/graphify-out/.graphify_python")
  (
    # Run AST-only graph update
    "$PYTHON" -m graphify update . > /dev/null 2>&1

    # Sync God Nodes + stats into main.mdc from the refreshed graph.json
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

    comm_ids = {n.get("community", n.get("group", -1)) for n in nodes if n.get("community", n.get("group")) is not None}
    n_communities = len(comm_ids)
    n_nodes = len(nodes)
    n_edges = len(links)

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
        r"(<!-- Last updated: )[\d-]+([^\d\n]+\d+ files[^\d\n]+)\d+( nodes[^\d\n]+)\d+( edges[^\d\n]+)\d+( communities -->)",
        lambda m: f"{m.group(1)}{ts}{m.group(2)}{n_nodes}{m.group(3)}{n_edges}{m.group(4)}{n_communities}{m.group(5)}",
        mdc
    )

    mdc = re.sub(
        r"(<!-- Last updated: )[\d-]+( -->)\n\n\|.*?\n\n(> Before touching)",
        f"\\g<1>{ts}\\g<2>\n\n{god_table}\n\n\\g<3>",
        mdc, flags=re.DOTALL
    )

    mdc_path.write_text(mdc)
except Exception as e:
    import sys
    print(f"graphify main.mdc sync error: {e}", file=sys.stderr)
PYEOF
    fi
  ) &
fi

# ── 9. gstack context-save (if available) ────────────────────────────────────
if command -v gstack-context-save >/dev/null 2>&1; then
  (gstack-context-save > /dev/null 2>&1) &
fi

# ── 10. Build graph impact summary for affected files ────────────────────────
graph_impact=""
export CHANGED_FILES="$raw_changed"
if [ -f "$REPO_ROOT/graphify-out/graph.json" ] && command -v python3 >/dev/null 2>&1; then
  graph_impact=$(python3 - "$REPO_ROOT/graphify-out/graph.json" "$REPO_ROOT" <<'PYEOF'
import json, sys, os
from collections import defaultdict, Counter

graph_file = sys.argv[1]
changed_files = [f.strip() for f in os.environ.get("CHANGED_FILES", "").splitlines() if f.strip()]

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
        return ""

    touched_communities = defaultdict(list)
    god_nodes_hit = []
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

    if not touched_communities:
        print("")
        sys.exit(0)

    parts = []
    comm_count = len(touched_communities)
    parts.append(f"Graph impact: {comm_count} {'community' if comm_count == 1 else 'communities'} touched.")
    for comm, labels in list(touched_communities.items())[:4]:
        sample = ", ".join(labels[:3])
        if len(labels) > 3:
            sample += f" (+{len(labels)-3} more)"
        parts.append(f"  • community {comm}: {sample}")
    if god_nodes_hit:
        parts.append(f"  ⚠ God nodes in blast radius: {', '.join(god_nodes_hit[:3])}")
    print("\n".join(parts))
except Exception:
    print("")
PYEOF
  ) 2>/dev/null || graph_impact=""
fi

# ── 11. Ask agent to fill in the session file ─────────────────────────────────
graph_note=""
if [ -n "$graph_impact" ]; then
  graph_note=" Graph context: ${graph_impact}. Query /graphify before writing decisions if any nodes are CRITICAL or HIGH risk."
fi

cat <<JSON
{"followup_message": "Session file created at \`${session_file}\` (${today} ${now}, topics: ${topics}).${graph_note} Fill in three sections: (1) ## What happened — 1-2 sentences on the task; (2) ## Decisions — 3-5 caveman bullets, the *why*; (3) ## What to pick up next — open threads or follow-ups. Keep the whole file under 50 lines."}
JSON
exit 0

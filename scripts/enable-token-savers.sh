#!/usr/bin/env bash
# Enable token-saving features for THIS repo (agent brief, tool compress, scout on stop).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$ROOT/.memory-graph" "$ROOT/memory"

EXAMPLE="$ROOT/.memory-graph/config.example.yaml"
CONFIG="$ROOT/.memory-graph/config.yaml"

if [[ ! -f "$CONFIG" ]]; then
  if [[ -f "$EXAMPLE" ]]; then
    cp "$EXAMPLE" "$CONFIG"
  else
    cat > "$CONFIG" <<'EOF'
track: auto
agent_brief: true
agent_brief_max_lines: 45
tool_output_compress: true
tool_output_min_chars: 6000
tool_output_max_summary: 1200
graph_scout_local: false
graph_scout_on_stop: true
graph_scout_budget: 500
EOF
  fi
fi

ensure_kv() {
  local key="$1"
  local val="$2"
  if grep -q "^${key}:" "$CONFIG" 2>/dev/null; then
    sed -i '' "s/^${key}:.*/${key}: ${val}/" "$CONFIG" 2>/dev/null || \
      sed -i "s/^${key}:.*/${key}: ${val}/" "$CONFIG"
  else
    echo "${key}: ${val}" >> "$CONFIG"
  fi
}

ensure_kv "agent_brief" "true"
ensure_kv "agent_brief_max_lines" "45"
ensure_kv "tool_output_compress" "true"
ensure_kv "tool_output_min_chars" "6000"
ensure_kv "tool_output_max_summary" "1200"
ensure_kv "graph_scout_on_stop" "true"
grep -q '^graph_scout_budget:' "$CONFIG" || ensure_kv "graph_scout_budget" "500"

chmod +x "$ROOT/.cursor/hooks/assemble-agent-brief.py" 2>/dev/null || true
chmod +x "$ROOT/.cursor/hooks/compress-tool-output.py" 2>/dev/null || true
chmod +x "$ROOT/.cursor/hooks/compress-tool-output.sh" 2>/dev/null || true
chmod +x "$ROOT/.cursor/hooks/on-session-start.sh" 2>/dev/null || true

echo "memory-graph: token savers enabled for this repo"
echo "  config: .memory-graph/config.yaml"
echo ""
echo "What you get:"
echo "  • memory/.agent-brief.yaml     — one file at task start (sessionStart injects it)"
echo "  • postToolUse compress         — large Shell/Grep/Read outputs summarized"
echo "  • graph_scout_on_stop         — precomputes scout when local scout enabled"
echo ""
echo "Also enable local graph scout (no subagent tokens):"
echo "  bash scripts/enable-graph-scout-local.sh"
echo ""
echo "Verify:"
echo "  REPO_ROOT=\"$ROOT\" python3 .cursor/hooks/assemble-agent-brief.py --check"
echo ""

REPO_ROOT="$ROOT" python3 "$ROOT/.cursor/hooks/assemble-agent-brief.py" --check || true

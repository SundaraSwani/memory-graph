#!/usr/bin/env bash
# Enable local graph scout for THIS repo (graphify traversal, no Cursor subagent tokens).
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
graph_scout_local: true
graph_scout_budget: 500
graph_scout_summarize: false
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

ensure_kv "graph_scout_local" "true"
grep -q '^graph_scout_on_stop:' "$CONFIG" || ensure_kv "graph_scout_on_stop" "true"
grep -q '^graph_scout_budget:' "$CONFIG" || ensure_kv "graph_scout_budget" "500"
grep -q '^graph_scout_summarize:' "$CONFIG" || ensure_kv "graph_scout_summarize" "false"

chmod +x "$ROOT/.cursor/hooks/graph-scout-local.py" 2>/dev/null || true
chmod +x "$ROOT/scripts/graph-scout-local.sh" 2>/dev/null || true

echo "memory-graph: local graph scout enabled for this repo"
echo "  config: .memory-graph/config.yaml"
echo ""
echo "At task start (code/architecture work):"
echo "  bash scripts/graph-scout-local.sh \"<files or concepts>\""
echo "  then read memory/.graph-scout.yaml (~500 tokens)"
echo ""
echo "Fallback: spawn graph-scout subagent if local scout fails or drill_subagent: true"
echo ""
echo "Optional Ollama one-line recommendation:"
echo "  Set graph_scout_summarize: true in config.yaml AND enable Ollama (ollama.yaml)"
echo ""
echo "Verify:"
echo "  REPO_ROOT=\"$ROOT\" python3 .cursor/hooks/graph-scout-local.py --check"
echo ""

REPO_ROOT="$ROOT" python3 "$ROOT/.cursor/hooks/graph-scout-local.py" --check || true

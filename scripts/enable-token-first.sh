#!/usr/bin/env bash
# Enable token-first profile: Ollama context gateway at session start, no scout auto-inject.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$ROOT/.memory-graph" "$ROOT/memory"

EXAMPLE="$ROOT/.memory-graph/config.example.yaml"
CONFIG="$ROOT/.memory-graph/config.yaml"
OLLAMA="$ROOT/.memory-graph/ollama.yaml"
OLLAMA_EXAMPLE="$ROOT/.memory-graph/ollama.example.yaml"

if [[ ! -f "$CONFIG" ]]; then
  if [[ -f "$EXAMPLE" ]]; then
    cp "$EXAMPLE" "$CONFIG"
  else
    cat > "$CONFIG" <<'EOF'
track: auto
agent_brief: true
agent_brief_max_lines: 20
tool_output_compress: true
tool_output_min_chars: 6000
tool_output_max_summary: 1200
graph_scout_local: false
graph_scout_on_stop: false
ollama_context_on_start: true
ollama_context_max_lines: 15
ollama_context_cache_mins: 30
ollama_context_max_chars: 1200
EOF
  fi
fi

if [[ ! -f "$OLLAMA" && -f "$OLLAMA_EXAMPLE" ]]; then
  cp "$OLLAMA_EXAMPLE" "$OLLAMA"
  sed -i '' 's/enabled: false/enabled: true/' "$OLLAMA" 2>/dev/null || \
    sed -i 's/enabled: false/enabled: true/' "$OLLAMA"
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
ensure_kv "agent_brief_max_lines" "20"
ensure_kv "graph_scout_on_stop" "false"
ensure_kv "tool_output_compress" "true"
ensure_kv "ollama_context_on_start" "true"
ensure_kv "ollama_context_max_lines" "15"
ensure_kv "ollama_context_cache_mins" "30"
ensure_kv "ollama_context_max_chars" "1200"

chmod +x "$ROOT/.cursor/hooks/ollama-context-gateway.py" 2>/dev/null || true
chmod +x "$ROOT/.cursor/hooks/on-session-start.sh" 2>/dev/null || true

echo "memory-graph: token-first profile enabled"
echo "  config: .memory-graph/config.yaml"
echo ""
echo "What you get:"
echo "  • Ollama precomputes memory/.cursor-context.yaml on session stop"
echo "  • sessionStart injects only that file (~1200 chars) — no graph scout"
echo "  • graph_scout_on_stop: false — run scout manually when needed"
echo ""
echo "Requires Ollama:"
echo "  bash scripts/enable-semantic-ollama.sh   # if ollama.yaml missing"
echo "  bash scripts/check-ollama.sh"
echo ""
echo "Verify:"
echo "  REPO_ROOT=\"$ROOT\" python3 .cursor/hooks/ollama-context-gateway.py --check"
echo "  REPO_ROOT=\"$ROOT\" python3 .cursor/hooks/ollama-context-gateway.py --dry-run"
echo ""

bash "$ROOT/scripts/check-ollama.sh" 2>/dev/null || true

#!/usr/bin/env bash
# sessionStart — inject slim Ollama context or agent brief (read-only, no LLM here).
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
CFG="$ROOT/.memory-graph/config.yaml"
CONTEXT="$ROOT/memory/.cursor-context.yaml"
BRIEF="$ROOT/memory/.agent-brief.yaml"
STATE="$ROOT/memory/state.yaml"

_cfg_true() {
  local key="$1"
  [[ -f "$CFG" ]] && grep -qE "^${key}:[[:space:]]*true" "$CFG" 2>/dev/null
}

_inject() {
  local file="$1"
  local max_chars="$2"
  local preamble="$3"
  REPO_ROOT="$ROOT" python3 - "$file" "$max_chars" "$preamble" <<'PYEOF'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
max_chars = int(sys.argv[2])
preamble = sys.argv[3]
text = path.read_text(encoding="utf-8", errors="replace").strip()
if len(text) > max_chars:
    text = text[:max_chars] + "\n# ... (truncated for sessionStart injection)"
print(json.dumps({"additional_context": preamble + text}))
PYEOF
}

# Token-first: prefer precomputed Ollama gateway context (~1200 chars)
if _cfg_true "ollama_context_on_start" && [[ -f "$CONTEXT" ]]; then
  _inject "$CONTEXT" 1200 \
    "memory-graph: slim context below. Do NOT read memory/state.yaml, sessions/, or graph scout.\n\n"
  exit 0
fi

# Fallback when gateway enabled but cache missing: truncated state.yaml
if _cfg_true "ollama_context_on_start" && [[ -f "$STATE" ]]; then
  _inject "$STATE" 1200 \
    "memory-graph: working memory below (gateway cache missing). Do NOT read sessions/.\n\n"
  exit 0
fi

# Legacy: merged agent brief (state + optional scout)
if _cfg_true "agent_brief" && [[ -f "$BRIEF" ]]; then
  _inject "$BRIEF" 1800 \
    "memory-graph: project context below. Do NOT also read memory/state.yaml or memory/.graph-scout.yaml separately.\n\n"
  exit 0
fi

printf '{}\n'

#!/usr/bin/env bash
# sessionStart — inject agent brief into initial context (one read, not multiple files).
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
BRIEF="$ROOT/memory/.agent-brief.yaml"
CFG="$ROOT/.memory-graph/config.yaml"

_enabled() {
  [[ -f "$CFG" ]] || return 1
  grep -qE '^agent_brief:[[:space:]]*true' "$CFG" 2>/dev/null
}

if ! _enabled || [[ ! -f "$BRIEF" ]]; then
  printf '{}\n'
  exit 0
fi

# Cap injection size (~1500 chars) to limit session-start tokens
REPO_ROOT="$ROOT" python3 - "$BRIEF" <<'PYEOF'
import json, sys
from pathlib import Path

brief = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").strip()
max_chars = 1800
if len(brief) > max_chars:
    brief = brief[:max_chars] + "\n# ... (truncated for sessionStart injection)"

msg = (
    "memory-graph: project context below. Do NOT also read memory/state.yaml or "
    "memory/.graph-scout.yaml separately.\n\n" + brief
)
print(json.dumps({"additional_context": msg}))
PYEOF

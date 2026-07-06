#!/usr/bin/env bash
# memory-graph: afterFileEdit hook — append agent-edited paths to a session ledger.
# Used when MEMORY_TRACK=cursor|auto and for non-git projects.
set -uo pipefail

_input=$(cat)

REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "$0")/../.." && pwd))}"
cd "$REPO_ROOT"

_parse_field() {
  local key=$1
  if command -v jq >/dev/null 2>&1; then
    case "$key" in
      file_path)
        printf '%s' "$_input" | jq -r '.file_path // empty' 2>/dev/null || true
        ;;
      workspace_root)
        printf '%s' "$_input" | jq -r '.workspace_roots[0] // empty' 2>/dev/null || true
        ;;
    esac
  else
    printf '%s' "$_input" | python3 - "$key" <<'PY' 2>/dev/null || true
import json, sys
key = sys.argv[1]
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if key == "file_path":
    print(d.get("file_path") or "")
elif key == "workspace_root":
    roots = d.get("workspace_roots") or []
    print(roots[0] if roots else "")
PY
  fi
}

file_path="$(_parse_field file_path)"
workspace_root="$(_parse_field workspace_root)"

[[ -n "$file_path" ]] || exit 0

rel_path="$(
  REPO_ROOT="$REPO_ROOT" FILE_PATH="$file_path" WORKSPACE_ROOT="$workspace_root" python3 <<'PY'
import os
from pathlib import Path

repo = Path(os.environ["REPO_ROOT"]).resolve()
fp = Path(os.environ["FILE_PATH"])
ws = os.environ.get("WORKSPACE_ROOT", "").strip()
root = Path(ws).resolve() if ws else repo

if fp.is_absolute():
    try:
        rel = fp.relative_to(root)
    except ValueError:
        try:
            rel = fp.relative_to(repo)
        except ValueError:
            raise SystemExit(0)
else:
    rel = Path(fp)

print(str(rel).replace("\\", "/"))
PY
)" || exit 0

[[ -n "$rel_path" ]] || exit 0

# Same exclusions as on-session-end (avoid feedback loops)
case "$rel_path" in
  .cursor/*|sessions/*|memory.md|graphify-out/*) exit 0 ;;
esac

mkdir -p "$REPO_ROOT/.memory-graph"
ledger="$REPO_ROOT/.memory-graph/changed-files"

if [[ -f "$ledger" ]] && grep -Fxq "$rel_path" "$ledger" 2>/dev/null; then
  exit 0
fi

printf '%s\n' "$rel_path" >> "$ledger"
exit 0

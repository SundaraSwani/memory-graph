#!/usr/bin/env bash
# Check local graph scout setup.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY="$ROOT/.cursor/hooks/graph-scout-local.py"

if [[ ! -f "$PY" ]]; then
  echo "Missing $PY" >&2
  exit 1
fi

REPO_ROOT="$ROOT" python3 "$PY" --check
exit $?

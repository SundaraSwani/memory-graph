#!/usr/bin/env bash
# Launch Memory Observatory — cross-repo memory-graph dashboard.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
DASH="$ROOT/dashboard"

if [[ ! -f "$DASH/serve.py" ]]; then
  # Dev layout: scripts at project root, toolkit in memory-graph/
  if [[ -f "$SCRIPT_DIR/../memory-graph/dashboard/serve.py" ]]; then
    DASH=$(cd "$SCRIPT_DIR/../memory-graph/dashboard" && pwd)
  else
    echo "error: dashboard not found. Run setup or upgrade-memory-graph.sh" >&2
    exit 1
  fi
fi

HOST="${OBSERVATORY_HOST:-127.0.0.1}"
PORT="${OBSERVATORY_PORT:-8765}"

if [[ -z "${OBSERVATORY_ROOTS:-}" && ! -f "$HOME/.memory-graph/observatory.yaml" ]]; then
  echo "[info] Using default scan roots (Desktop, Documents, …). Override:"
  echo "       OBSERVATORY_ROOTS=~/Desktop:~/code bash $0"
  echo "       or create ~/.memory-graph/observatory.yaml with a roots: list"
fi

exec python3 "$DASH/serve.py" --host "$HOST" --port "$PORT"

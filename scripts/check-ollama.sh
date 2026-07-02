#!/usr/bin/env bash
# Check local Ollama for semantic memory compression.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OLLAMA_PY="$ROOT/.cursor/hooks/semantic-compress-ollama.py"

if [[ ! -f "$ROOT/.memory-graph/ollama.yaml" ]]; then
  echo "Ollama semantic compress: not configured for this repo."
  echo ""
  echo "Enable (per-repo, optional):"
  echo "  bash scripts/enable-semantic-ollama.sh"
  echo ""
  echo "Requires: https://ollama.com — install, then: ollama serve && ollama pull llama3.2:3b"
  exit 1
fi

if [[ ! -f "$OLLAMA_PY" ]]; then
  echo "Missing $OLLAMA_PY" >&2
  exit 1
fi

REPO_ROOT="$ROOT" python3 "$OLLAMA_PY" --check
exit $?

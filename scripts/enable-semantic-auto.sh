#!/usr/bin/env bash
# Enable automatic semantic-compress followup from the session hook when structural memory hits caps.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
touch "$ROOT/.memory-graph-semantic-auto"
echo "[ok] Semantic auto enabled — hook may emit one followup when memory/.semantic-pending appears"
echo ""
echo "Disable: rm .memory-graph-semantic-auto"
echo "Or env per session: MEMORY_SEMANTIC_AUTO=1"
echo ""
echo "Alternative (no Cursor tokens): bash scripts/enable-semantic-ollama.sh"
echo ""
echo "Thresholds (override via env):"
echo "  MEMORY_SEMANTIC_INTERVAL_DAYS=7"
echo "  MEMORY_SEMANTIC_ARCHIVE_BYTES=50000"

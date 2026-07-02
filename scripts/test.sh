#!/usr/bin/env bash
# memory-graph test suite — sandbox + static. Safe to run before git push.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

echo "memory-graph tests"
echo "──────────────────"

bash "$ROOT/scripts/test-static.sh"
echo ""
bash "$ROOT/scripts/test-compress-sandbox.sh"

echo ""
echo "All tests passed."

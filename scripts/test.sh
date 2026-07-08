#!/usr/bin/env bash
# memory-graph test suite — sandbox + static. Safe to run before git push.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

echo "memory-graph tests"
echo "──────────────────"

bash "$ROOT/scripts/test-static.sh"
echo ""
echo "== unit tests =="
python3 -m unittest discover -s "$ROOT/tests" -t "$ROOT" -q
echo ""
bash "$ROOT/scripts/test-compress-sandbox.sh"

echo ""
echo "All tests passed."

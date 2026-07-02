#!/usr/bin/env bash
# Static checks — no sandbox, fast. Run on every push.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

fail() { echo "FAIL: $1" >&2; exit 1; }

echo "== static: required files =="
for f in \
  .cursor/hooks/on-session-end.sh \
  .cursor/hooks/compress-memory.py \
  .cursor/hooks.json \
  .cursor/rules/main.mdc \
  .cursor/rules/sdlc.mdc \
  post-commit.sh \
  setup \
  .agents/skills/semantic-compress/SKILL.md \
  .agents/skills/ship-feature/SKILL.md \
  .agents/skills/graph-scout/SKILL.md \
  .memory-graph/ollama.example.yaml \
  .cursor/hooks/semantic-compress-ollama.py \
  scripts/enable-semantic-auto.sh \
  scripts/enable-semantic-ollama.sh \
  scripts/check-ollama.sh \
  docs/cheat-sheet.md \
  scripts/test.sh \
  scripts/test-compress-sandbox.sh; do
  [ -f "$f" ] || fail "missing $f"
done

echo "== static: shell syntax =="
for f in \
  .cursor/hooks/on-session-end.sh \
  .cursor/hooks/memory-update.sh \
  .cursor/hooks/graphify-update.sh \
  post-commit.sh \
  setup \
  scripts/test.sh \
  scripts/test-static.sh \
  scripts/test-compress-sandbox.sh \
  scripts/check-ollama.sh \
  scripts/enable-semantic-ollama.sh; do
  [ -f "$f" ] && bash -n "$f" || fail "bash -n $f"
done

echo "== static: python syntax =="
python3 -m py_compile .cursor/hooks/compress-memory.py
python3 -m py_compile .cursor/hooks/semantic-compress-ollama.py

echo "== static: hook contract =="
if grep -v '^[[:space:]]*#' .cursor/hooks/on-session-end.sh | grep -q 'Fill in three sections'; then
  fail "on-session-end.sh must not emit session-capture followup (extra agent turns)"
fi
if grep -v '^[[:space:]]*#' .cursor/hooks/on-session-end.sh | grep -q 'followup_message'; then
  grep -q '_maybe_semantic_followup' .cursor/hooks/on-session-end.sh || \
    fail "followup_message only allowed for opt-in semantic auto (_maybe_semantic_followup)"
fi
grep -q 'alwaysApply: false' .cursor/rules/sdlc.mdc || \
  fail "sdlc.mdc must be opt-in (alwaysApply: false)"
grep -q 'alwaysApply: true' .cursor/rules/main.mdc || \
  fail "main.mdc must stay always-on (alwaysApply: true)"
grep -q "compress-memory.py" .cursor/hooks/on-session-end.sh || \
  fail "on-session-end.sh must invoke compress-memory.py"
grep -q '_maybe_semantic_ollama' .cursor/hooks/on-session-end.sh || \
  fail "on-session-end.sh must support optional Ollama semantic compress"

echo "OK — static checks passed"

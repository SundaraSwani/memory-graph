#!/usr/bin/env bash
# Static checks — no sandbox, fast. Run on every push.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

fail() { echo "FAIL: $1" >&2; exit 1; }

echo "== static: required files =="
for f in \
  .cursor/hooks/on-session-end.sh \
  .cursor/hooks/track-changed-files.sh \
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
  .memory-graph/config.example.yaml \
  .cursor/hooks/semantic-compress-ollama.py \
  .cursor/hooks/graph-scout-local.py \
  .cursor/hooks/assemble-agent-brief.py \
  .cursor/hooks/compress-tool-output.py \
  .cursor/hooks/on-session-start.sh \
  .cursor/hooks/fill-session-from-transcript.py \
  .cursor/hooks/ollama-context-gateway.py \
  scripts/enable-semantic-auto.sh \
  scripts/enable-semantic-ollama.sh \
  scripts/check-ollama.sh \
  scripts/graph-scout-local.sh \
  scripts/enable-graph-scout-local.sh \
  scripts/check-graph-scout-local.sh \
  scripts/enable-token-first.sh \
  docs/cheat-sheet.md \
  scripts/test.sh \
  scripts/test-compress-sandbox.sh \
  scripts/enable-token-first.sh \
  scripts/upgrade-memory-graph.sh; do
  [ -f "$f" ] || fail "missing $f"
done

echo "== static: shell syntax =="
for f in \
  .cursor/hooks/on-session-end.sh \
  .cursor/hooks/track-changed-files.sh \
  .cursor/hooks/memory-update.sh \
  .cursor/hooks/graphify-update.sh \
  post-commit.sh \
  setup \
  scripts/test.sh \
  scripts/test-static.sh \
  scripts/test-compress-sandbox.sh \
  scripts/check-ollama.sh \
  scripts/enable-semantic-ollama.sh \
  scripts/graph-scout-local.sh \
  scripts/enable-graph-scout-local.sh \
  scripts/check-graph-scout-local.sh \
  scripts/enable-token-savers.sh \
  scripts/enable-token-first.sh \
  scripts/upgrade-memory-graph.sh \
  .cursor/hooks/compress-tool-output.sh \
  .cursor/hooks/on-session-start.sh; do
  [ -f "$f" ] && bash -n "$f" || fail "bash -n $f"
done

echo "== static: python syntax =="
python3 -m py_compile .cursor/hooks/compress-memory.py
python3 -m py_compile .cursor/hooks/semantic-compress-ollama.py
python3 -m py_compile .cursor/hooks/graph-scout-local.py
python3 -m py_compile .cursor/hooks/assemble-agent-brief.py
python3 -m py_compile .cursor/hooks/compress-tool-output.py
python3 -m py_compile .cursor/hooks/fill-session-from-transcript.py
python3 -m py_compile .cursor/hooks/ollama-context-gateway.py

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
grep -q 'postToolUse' .cursor/hooks.json || fail "hooks.json must register postToolUse tool compress"
grep -q 'sessionStart' .cursor/hooks.json || fail "hooks.json must register sessionStart agent brief"
grep -q 'agent_brief' .memory-graph/config.example.yaml || \
  fail "config.example.yaml must document agent_brief"
grep -q 'agent-brief' .cursor/rules/main.mdc || \
  fail "main.mdc must document agent brief"
grep -q '_collect_changed_files' .cursor/hooks/on-session-end.sh || \
  fail "on-session-end.sh must support git + cursor change tracking"
grep -q 'fill-session-from-transcript' .cursor/hooks/on-session-end.sh || \
  fail "on-session-end.sh must fill session fields from transcript"
grep -q 'session_fill_from_transcript' .memory-graph/config.example.yaml || \
  fail "config.example.yaml must document session_fill_from_transcript"
grep -q 'afterFileEdit' .cursor/hooks.json || \
  fail "hooks.json must register afterFileEdit tracker"
grep -q 'ollama-context-gateway' .cursor/hooks/on-session-end.sh || \
  fail "on-session-end.sh must precompute Ollama context gateway"
grep -q '.cursor-context.yaml' .cursor/hooks/on-session-start.sh || \
  fail "on-session-start.sh must inject cursor-context when enabled"
grep -q 'ollama_context_on_start' .memory-graph/config.example.yaml || \
  fail "config.example.yaml must document ollama_context_on_start"

echo "OK — static checks passed"

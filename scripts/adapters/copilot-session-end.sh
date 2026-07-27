#!/usr/bin/env bash
# memory-graph: Copilot sessionEnd adapter
# Reads Copilot's JSON payload from stdin and calls the shared pipeline.
#
# Copilot payload (camelCase):
#   { sessionId, timestamp, cwd, reason, transcriptPath? }
#
# Maps to Cursor-style env vars for compatibility with existing hooks.

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Read Copilot JSON from stdin
_input=$(cat)

# Extract fields from Copilot payload
if command -v jq >/dev/null 2>&1; then
  TRANSCRIPT_PATH="$(printf '%s' "$_input" | jq -r '.transcriptPath // empty' 2>/dev/null || true)"
  REASON="$(printf '%s' "$_input" | jq -r '.reason // "complete"' 2>/dev/null || echo complete)"
  CWD="$(printf '%s' "$_input" | jq -r '.cwd // empty' 2>/dev/null || true)"
else
  # Fallback: basic grep parsing
  TRANSCRIPT_PATH=""
  REASON="complete"
  CWD=""
fi

# Skip if session ended due to error/abort (similar to Cursor's status check)
if [[ "$REASON" == "error" || "$REASON" == "abort" ]]; then
  printf '{}'
  exit 0
fi

# Export for downstream scripts
export COPILOT_TRANSCRIPT_PATH="$TRANSCRIPT_PATH"
export COPILOT_SESSION_REASON="$REASON"
export IDE_SOURCE="copilot"

# Transform Copilot payload to Cursor-compatible format for the shared pipeline
# The existing on-session-end.sh reads: { loop_count, status, transcript_path }
cursor_payload=$(cat <<JSON
{
  "loop_count": 0,
  "status": "completed",
  "transcript_path": "$TRANSCRIPT_PATH"
}
JSON
)

# Call the shared pipeline (reuse existing Cursor hook logic)
if [[ -f "$REPO_ROOT/.cursor/hooks/on-session-end.sh" ]]; then
  printf '%s' "$cursor_payload" | bash "$REPO_ROOT/.cursor/hooks/on-session-end.sh"
else
  # Fallback: minimal session tracking without full Cursor hooks
  printf '{}'
fi

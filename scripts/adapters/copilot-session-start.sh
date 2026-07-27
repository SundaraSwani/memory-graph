#!/usr/bin/env bash
# memory-graph: Copilot sessionStart adapter
# Reads Copilot's JSON payload from stdin, calls shared pipeline, wraps output.
#
# Copilot payload (camelCase):
#   { sessionId, timestamp, cwd, source, initialPrompt? }
#
# Copilot expects output:
#   { "additionalContext": "..." }
#
# The existing on-session-start.sh outputs: { "additional_context": "..." }
# We need to transform the key from snake_case to camelCase.

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Read Copilot JSON from stdin (we don't use it much for start, but capture it)
_input=$(cat)

# Export IDE source for any downstream scripts that care
export IDE_SOURCE="copilot"

# Call the shared pipeline
if [[ -f "$REPO_ROOT/.cursor/hooks/on-session-start.sh" ]]; then
  result=$(bash "$REPO_ROOT/.cursor/hooks/on-session-start.sh" 2>/dev/null || echo '{}')
  
  # Transform snake_case key to camelCase for Copilot
  # Cursor: { "additional_context": "..." }
  # Copilot: { "additionalContext": "..." }
  if command -v jq >/dev/null 2>&1; then
    context=$(printf '%s' "$result" | jq -r '.additional_context // empty' 2>/dev/null || true)
    if [[ -n "$context" ]]; then
      # Escape for JSON and output
      printf '%s' "$context" | jq -Rs '{ additionalContext: . }'
    else
      printf '{}\n'
    fi
  else
    # Fallback: basic sed transform
    printf '%s' "$result" | sed 's/"additional_context"/"additionalContext"/g'
  fi
else
  printf '{}\n'
fi

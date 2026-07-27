#!/usr/bin/env bash
# memory-graph: Copilot postToolUse adapter
# Compresses large tool outputs to save tokens.
#
# Copilot payload (PostToolUse):
#   { sessionId, timestamp, cwd, toolName, toolArgs, toolResult: { resultType, textResultForLlm } }
#
# Copilot expects output:
#   { modifiedResult?: { resultType, textResultForLlm }, additionalContext?: string }

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Read Copilot JSON from stdin
_input=$(cat)

# Extract tool result
if command -v jq >/dev/null 2>&1; then
  TOOL_NAME="$(printf '%s' "$_input" | jq -r '.toolName // empty' 2>/dev/null || true)"
  TOOL_RESULT="$(printf '%s' "$_input" | jq -r '.toolResult.textResultForLlm // empty' 2>/dev/null || true)"
else
  printf '{}\n'
  exit 0
fi

# Skip if no result or small result
result_len=${#TOOL_RESULT}
if [[ $result_len -lt 5000 ]]; then
  printf '{}\n'
  exit 0
fi

# Export for the compression script
export TOOL_NAME="$TOOL_NAME"
export IDE_SOURCE="copilot"

# Call the shared compression script if it exists
if [[ -f "$REPO_ROOT/.cursor/hooks/compress-tool-output.py" ]]; then
  compressed=$(printf '%s' "$TOOL_RESULT" | REPO_ROOT="$REPO_ROOT" python3 "$REPO_ROOT/.cursor/hooks/compress-tool-output.py" 2>/dev/null || echo "")
  
  if [[ -n "$compressed" && "$compressed" != "$TOOL_RESULT" ]]; then
    # Return modified result
    jq -n --arg text "$compressed" '{
      modifiedResult: {
        resultType: "success",
        textResultForLlm: $text
      }
    }'
  else
    printf '{}\n'
  fi
else
  printf '{}\n'
fi

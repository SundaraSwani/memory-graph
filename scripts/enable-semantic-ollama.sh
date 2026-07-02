#!/usr/bin/env bash
# Enable local Ollama semantic compression for THIS git repo only.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$ROOT/.memory-graph"

EXAMPLE="$ROOT/.memory-graph/ollama.example.yaml"
CONFIG="$ROOT/.memory-graph/ollama.yaml"

if [[ ! -f "$CONFIG" ]]; then
  if [[ -f "$EXAMPLE" ]]; then
    cp "$EXAMPLE" "$CONFIG"
  else
    cat > "$CONFIG" <<'EOF'
enabled: true
host: http://127.0.0.1:11434
model: llama3.2:3b
max_archive_chars: 12000
timeout: 120
EOF
  fi
fi

# Ensure enabled
if grep -q '^enabled:' "$CONFIG"; then
  sed -i '' 's/^enabled:.*/enabled: true/' "$CONFIG" 2>/dev/null || \
    sed -i 's/^enabled:.*/enabled: true/' "$CONFIG"
else
  echo "enabled: true" | cat - "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"
fi

chmod +x "$ROOT/.cursor/hooks/semantic-compress-ollama.py" 2>/dev/null || true
chmod +x "$ROOT/scripts/check-ollama.sh" 2>/dev/null || true

echo "memory-graph: Ollama semantic compress enabled for this repo"
echo "  config: .memory-graph/ollama.yaml"
echo ""
echo "Prerequisites:"
echo "  1. Install Ollama — https://ollama.com/download"
echo "  2. Start server:   ollama serve"
echo "  3. Pull a model:   ollama pull llama3.2:3b"
echo "     (edit model in .memory-graph/ollama.yaml if you prefer another)"
echo ""
echo "Verify:"
echo "  bash scripts/check-ollama.sh"
echo ""
echo "When structural memory hits caps, the session hook runs Ollama automatically"
echo "(no Cursor agent followup). Status → memory/.semantic-ollama-status"
echo ""
echo "Disable for this repo:"
echo "  Set enabled: false in .memory-graph/ollama.yaml"
echo "  Or: rm .memory-graph/ollama.yaml"
echo ""

bash "$ROOT/scripts/check-ollama.sh" || true

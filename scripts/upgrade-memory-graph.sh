#!/usr/bin/env bash
# Upgrade an existing memory-graph install — hooks, scripts, and .agents only.
#
# Preserves user data: memory/, sessions/, memory.md, .memory-graph/config.yaml,
# .memory-graph/ollama.yaml, .cursor/rules/, .cursor/hooks.json, graphify-out/
#
# Usage:
#   cd /your/project
#   bash memory-graph/scripts/upgrade-memory-graph.sh          # upgrade cwd
#   bash memory-graph/scripts/upgrade-memory-graph.sh /path    # upgrade target
#   bash ~/.cursor/skills/memory-graph/scripts/upgrade-memory-graph.sh
#
# Env:
#   MEMORY_GRAPH_SOURCE  — toolkit root (auto-detected if unset)
#   DRY_RUN=1            — print actions, do not copy

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
TARGET="${1:-$(pwd)}"
TARGET=$(cd "$TARGET" && pwd)
DRY_RUN="${DRY_RUN:-0}"

fail() { echo "error: $1" >&2; exit 1; }
info() { echo "[upgrade] $*"; }
warn() { echo "[warn] $*" >&2; }

_resolve_source() {
  local target=${1:-}

  if [[ -n "${MEMORY_GRAPH_SOURCE:-}" ]]; then
    local src
    src=$(cd "$MEMORY_GRAPH_SOURCE" && pwd)
    [[ -f "$src/.cursor/hooks/on-session-end.sh" ]] || fail "MEMORY_GRAPH_SOURCE has no hooks: $src"
    echo "$src"
    return
  fi

  # Script lives in <toolkit>/scripts/ — prefer toolkit adjacent to this script
  local candidate
  candidate=$(cd "$SCRIPT_DIR/.." && pwd)
  if [[ -f "$candidate/.cursor/hooks/on-session-end.sh" && "$candidate" != "$target" ]]; then
    echo "$candidate"
    return
  fi

  # Dev layout: installed at project root, toolkit kept in memory-graph/
  if [[ -n "$target" && -f "$target/memory-graph/.cursor/hooks/on-session-end.sh" ]]; then
    cd "$target/memory-graph" && pwd
    return
  fi

  fail "Could not find toolkit source. Set MEMORY_GRAPH_SOURCE=/path/to/memory-graph"
}

_is_installed() {
  local root=$1
  [[ -f "$root/.cursor/hooks/on-session-end.sh" ]] || \
  [[ -f "$root/.cursor/hooks/compress-memory.py" ]] || \
  { [[ -f "$root/post-commit.sh" ]] && [[ -d "$root/.memory-graph" ]]; }
}

_copy_file() {
  local src=$1 dest=$2
  if [[ "$DRY_RUN" == "1" ]]; then
    info "would copy: ${dest#"$TARGET"/}"
    return
  fi
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
}

_copy_tree() {
  local src_dir=$1 dest_dir=$2
  if [[ ! -d "$src_dir" ]]; then
    return
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    find "$src_dir" -type f \
      ! -path '*/__pycache__/*' ! -name '*.pyc' \
      | while read -r f; do
      info "would copy: ${dest_dir#"$TARGET"/}/${f#"$src_dir"/}"
    done
    return
  fi
  mkdir -p "$dest_dir"
  find "$src_dir" -type f \
    ! -path '*/__pycache__/*' ! -name '*.pyc' \
    | while read -r f; do
    local rel="${f#"$src_dir"/}"
    mkdir -p "$dest_dir/$(dirname "$rel")"
    cp "$f" "$dest_dir/$rel"
  done
}

_chmod_hooks_and_scripts() {
  [[ "$DRY_RUN" == "1" ]] && return
  chmod +x "$TARGET/setup" "$TARGET/post-commit.sh" 2>/dev/null || true
  find "$TARGET/.cursor/hooks" -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod +x {} + 2>/dev/null || true
  find "$TARGET/scripts" -type f -name '*.sh' -exec chmod +x {} + 2>/dev/null || true
}

SOURCE=$(_resolve_source "$TARGET")

if [[ "$SOURCE" == "$TARGET" ]]; then
  fail "Source and target are the same ($TARGET). Add a memory-graph/ toolkit subfolder or set MEMORY_GRAPH_SOURCE."
fi

if ! _is_installed "$TARGET"; then
  echo "No memory-graph install detected in $TARGET" >&2
  echo "Run full setup instead:" >&2
  echo "  bash \"$SOURCE/setup\"" >&2
  exit 1
fi

info "source: $SOURCE"
info "target: $TARGET"
[[ "$DRY_RUN" == "1" ]] && warn "DRY_RUN=1 — no files will change"

# ── Code: hooks ─────────────────────────────────────────────────────────────
if [[ -d "$SOURCE/.cursor/hooks" ]]; then
  _copy_tree "$SOURCE/.cursor/hooks" "$TARGET/.cursor/hooks"
  info "updated .cursor/hooks/"
fi

# ── Code: project scripts ───────────────────────────────────────────────────
if [[ -d "$SOURCE/scripts" ]]; then
  _copy_tree "$SOURCE/scripts" "$TARGET/scripts"
  info "updated scripts/"
fi

# ── Code: root executables ──────────────────────────────────────────────────
for f in setup post-commit.sh; do
  if [[ -f "$SOURCE/$f" ]]; then
    _copy_file "$SOURCE/$f" "$TARGET/$f"
    info "updated $f"
  fi
done

# ── Code: docs + example configs (not live config) ──────────────────────────
if [[ -d "$SOURCE/docs" ]]; then
  _copy_tree "$SOURCE/docs" "$TARGET/docs"
  info "updated docs/"
fi

mkdir -p "$TARGET/.memory-graph"
for f in config.example.yaml ollama.example.yaml; do
  if [[ -f "$SOURCE/.memory-graph/$f" ]]; then
    _copy_file "$SOURCE/.memory-graph/$f" "$TARGET/.memory-graph/$f"
    info "updated .memory-graph/$f"
  fi
done

# ── Agents: skills only ─────────────────────────────────────────────────────
if [[ -d "$SOURCE/.agents" ]]; then
  _copy_tree "$SOURCE/.agents" "$TARGET/.agents"
  info "updated .agents/"
fi

_chmod_hooks_and_scripts

echo ""
info "Done — upgraded code + .agents in $TARGET"
echo ""
echo "Preserved (not touched):"
echo "  memory/  sessions/  memory.md"
echo "  .memory-graph/config.yaml  .memory-graph/ollama.yaml"
echo "  .cursor/rules/  .cursor/hooks.json  graphify-out/"
echo ""
echo "Optional: bash scripts/test.sh"

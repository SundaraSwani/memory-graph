# memory-graph: Step-by-Step Installation Guide

Complete guide to install and use memory-graph with Cursor, Copilot, or both—from scratch or on existing projects.

---

## Quick Start

### For new projects (any IDE)

```bash
cd /your/project
curl -sL https://github.com/SundaraSwani/memory-graph/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1 && bash setup --ide=both
/graphify .
```

### For existing Cursor projects (add Copilot)

```bash
cd /your/project
bash setup --ide=both
```

### For existing Copilot projects (add Cursor)

```bash
cd /your/project
bash setup --ide=both
```

---

## Scenarios

### Scenario 1: Fresh Install — Cursor Only

**Goal:** Set up memory-graph for Cursor agent in a new project.

```bash
# 1. Clone/extract toolkit into project
cd /my/project
curl -sL https://github.com/SundaraSwani/memory-graph/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1

# 2. Run setup (defaults to Cursor)
bash setup

# 3. Build knowledge graph (once)
/graphify .

# 4. Start using
# Cursor now automatically:
# - Tracks session changes
# - Compresses memory
# - Injects agent brief at session start
```

**What got installed:**
- `.cursor/hooks/` — Cursor lifecycle scripts (session start/end, file edits, tool use)
- `.cursor/hooks.json` — Hook registration
- `scripts/` — Utilities (test runners, enablers)
- `.agents/skills/` — Team knowledge (conventions, workflows)
- `memory/` — Living state (agent brief, compressed state)
- `sessions/` — Session index

**Next steps:**
```bash
# Optional: reduce token usage
bash scripts/enable-token-savers.sh      # agent brief + tool compress
bash scripts/enable-token-first.sh       # Ollama gateway (fastest)
bash scripts/enable-graph-scout-local.sh # local graph queries

# Optional: Ollama semantic compression
bash scripts/enable-semantic-ollama.sh
bash scripts/check-ollama.sh
```

---

### Scenario 2: Fresh Install — Copilot Only

**Goal:** Set up memory-graph for Copilot in a new project.

```bash
# 1. Clone/extract toolkit
cd /my/project
curl -sL https://github.com/SundaraSwani/memory-graph/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1

# 2. Run setup for Copilot only
bash setup --ide=copilot

# 3. Build knowledge graph
/graphify .

# 4. In Copilot, enable hooks
# Copy .github/hooks/memory-graph.json to your Copilot CLI or VS Code config
# See: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks

# 5. Restart Copilot and start using
```

**What got installed:**
- `.github/hooks/memory-graph.json` — Copilot hook config (sessionStart/End/postToolUse)
- `.github/copilot-instructions.md` — Always-on context (mirrors main.mdc)
- `scripts/adapters/` — Copilot payload translators
  - `copilot-session-start.sh` — transforms `additional_context` → `additionalContext`
  - `copilot-session-end.sh` — calls shared `.cursor/hooks/on-session-end.sh`
  - `copilot-post-tool.sh` — compresses large tool outputs
- `.cursor/hooks/` — Shared pipeline (Copilot adapters call these)
- `memory/`, `sessions/` — Same as Cursor

**Why adapters?** One codebase for both IDEs. Copilot sends JSON payloads → adapters translate → shared Cursor hooks handle logic.

---

### Scenario 3: Existing Cursor Setup — Add Copilot

**Goal:** Enable memory-graph for Copilot while keeping existing Cursor setup.

```bash
# Option A: Automatic (recommended)
cd /my/project
bash setup --ide=both

# Option B: Manual (if you need to inspect first)
mkdir -p .github/hooks scripts/adapters
cp ~/.cursor/skills/memory-graph/.github/hooks/memory-graph.json .github/hooks/
cp ~/.cursor/skills/memory-graph/.github/copilot-instructions.md .github/
cp ~/.cursor/skills/memory-graph/scripts/adapters/*.sh scripts/adapters/
chmod +x scripts/adapters/*.sh
```

**What changes:**
- New `.github/` directory with Copilot config + instructions
- New `scripts/adapters/` with three shell scripts
- **No changes** to existing `.cursor/` or `memory/` — fully backward compatible

**Verify setup:**
```bash
# Check files exist
ls -la .github/hooks/memory-graph.json
ls -la scripts/adapters/copilot-*.sh

# Test in isolation (optional)
echo '{"sessionId":"test","timestamp":1234,"cwd":"'$PWD'","reason":"complete"}' \
  | bash scripts/adapters/copilot-session-end.sh
# Should output: {}
```

---

### Scenario 4: Existing Copilot Setup — Add Cursor

**Goal:** Enable memory-graph for Cursor while keeping existing Copilot setup.

```bash
# Automatic
cd /my/project
bash setup --ide=both

# Or manual: just copy Cursor hooks + scripts
mkdir -p .cursor/hooks
cp ~/.cursor/skills/memory-graph/.cursor/hooks/*.sh .cursor/hooks/
cp ~/.cursor/skills/memory-graph/.cursor/hooks/*.py .cursor/hooks/
cp ~/.cursor/skills/memory-graph/.cursor/hooks.json .cursor/
chmod +x .cursor/hooks/*.sh .cursor/hooks/*.py
```

**What changes:**
- New `.cursor/` directory with hooks + hook registration
- New `.cursor/rules/` with `main.mdc` and `sdlc.mdc`
- Existing `.github/` and `memory/` shared with Copilot

---

### Scenario 5: Both IDEs — Upgrade to Newer Toolkit

**Goal:** Update hooks, scripts, and skills while preserving memory, sessions, config.

```bash
cd /my/project
bash scripts/upgrade-memory-graph.sh

# or with explicit toolkit path (first time)
MEMORY_GRAPH_SOURCE=/path/to/memory-graph bash scripts/upgrade-memory-graph.sh

# or from toolkit directory
bash /path/to/memory-graph/scripts/upgrade-memory-graph.sh /my/project
```

**Preserved (not touched):**
- `memory/` — all memory state
- `sessions/` — session history
- `memory.md` — index
- `.memory-graph/config.yaml` — live config
- `.memory-graph/ollama.yaml` — Ollama settings
- `.cursor/rules/` — project-specific rules
- `.cursor/hooks.json` — custom hook modifications
- `graphify-out/` — knowledge graph

**Updated:**
- `.cursor/hooks/*.sh` — hook logic
- `.github/hooks/` — Copilot config
- `scripts/adapters/` — adapter logic
- `scripts/` — utilities
- `.agents/skills/` — team knowledge
- `docs/` — reference docs

---

## Architecture: How Adapters Work

### Cursor flow

```
Cursor event (sessionEnd)
    ↓
.cursor/hooks.json
    ↓
on-session-end.sh (reads stdin JSON, processes directly)
    ↓
compress-memory.py, session file creation, etc.
    ↓
memory/state.yaml updated
```

### Copilot flow

```
Copilot event (sessionEnd)
    ↓
.github/hooks/memory-graph.json
    ↓
copilot-session-end.sh (reads Copilot JSON)
    ↓
Transform: camelCase → snake_case payload
    ↓
.cursor/hooks/on-session-end.sh (shared logic)
    ↓
compress-memory.py, session file creation, etc.
    ↓
memory/state.yaml updated (same result)
```

**Key insight:** Copilot adapters are thin translators. They:
1. Read the Copilot JSON payload (camelCase)
2. Transform to Cursor format (snake_case)
3. Call the existing Cursor hook
4. Transform output back to Copilot format (camelCase)

Result: **One memory, two IDEs. Code changes work for both automatically.**

---

## Understanding Memory Tiers

All data is stored in `memory/` and `sessions/`.

| Tier | Path | Who writes | When | Size |
|------|------|-----------|------|------|
| **Brief** | `memory/.agent-brief.yaml` | `assemble-agent-brief.py` | At session end | ~1800 chars |
| **Hot** | `memory/state.yaml` | `compress-memory.py` | Every session end | ~3KB |
| **Warm** | `sessions/2026-07-08-1.md` | `on-session-end.sh` | Session end (if files changed) | ~1KB |
| **Cold** | `sessions/archive/2026-07.yaml` | `compress-memory.py` | Daily (automatic) | ~2KB |

**Agents read in order:**
1. At session start → `.agent-brief.yaml` (injected as `additionalContext`)
2. During turn → `memory/state.yaml` (for context)
3. On question → `sessions/` (recent history)
4. On demand → `graphify-out/GRAPH_REPORT.md` (via graph scout)

---

## Configuration

### Minimal setup

No config needed. Defaults work for most projects:
- Track changes via Cursor ledger (`.memory-graph/changed-files`)
- Compress memory every session
- Create session files when 3+ files changed
- No Ollama (not required)

### Recommended (token savers)

```bash
# Enable agent brief (fallback when Ollama unavailable)
bash scripts/enable-token-savers.sh

# Enable Ollama gateway (fastest, most efficient)
bash scripts/enable-token-first.sh
```

### Advanced (Ollama semantic compression)

```bash
# Install Ollama (macOS)
brew install ollama
ollama pull llama3.2:3b

# Enable in project
bash scripts/enable-semantic-ollama.sh
bash scripts/check-ollama.sh
```

**Config file:** `.memory-graph/config.yaml` (generated from template)

---

## Testing

Before committing or pushing:

```bash
# Full test suite (pytest + unittest)
bash scripts/test.sh

# Fast checks only (static analysis, contracts)
bash scripts/test-static.sh

# Pre-push hook runs automatically
git push
```

All tests must pass with zero network or LLM calls.

---

## Common Commands

```bash
# Graph operations
/graphify .                    # build graph + populate main.mdc
graphify update .              # update graph (AST-only, fast)

# Memory operations
python3 .cursor/hooks/compress-memory.py              # manual compress
python3 .cursor/hooks/compress-memory.py --check-semantic  # check if semantic needed

# Ollama (if enabled)
REPO_ROOT=. python3 .cursor/hooks/ollama-context-gateway.py --check
bash scripts/check-ollama.sh

# Upgrade
bash scripts/upgrade-memory-graph.sh

# Tests
bash scripts/test.sh
git push  # runs pre-push hook
```

---

## Troubleshooting

### "Adapter not found" error

**Symptom:** Copilot hook fails with "adapters/copilot-session-end.sh: not found"

**Fix:**
```bash
cd /your/project
ls -la scripts/adapters/
# If missing, re-run setup
bash setup --ide=both
```

### Memory growing too fast

**Symptom:** `memory/state.yaml` >10KB

**Fix:**
```bash
# Automatic compression (recommended)
bash scripts/enable-semantic-ollama.sh

# Or manual compression
python3 .cursor/hooks/compress-memory.py
# Then manually edit memory/state.yaml to ≤15 lines, delete old sessions/archive/
```

### Graph not updating

**Symptom:** `graphify-out/GRAPH_REPORT.md` is stale

**Fix:**
```bash
graphify update .
# or with LLM (slower, recommended once)
/graphify .
```

### Hooks not firing

**Symptom:** No session files created, memory not updating

**Fix (Cursor):**
```bash
# Check hooks are registered
cat .cursor/hooks.json | grep -E "sessionStart|stop|afterFileEdit"

# Verify hook paths are relative
# Hooks should call: .cursor/hooks/on-session-end.sh (not absolute paths)

# Restart Cursor
```

**Fix (Copilot):**
```bash
# Verify .github/hooks/memory-graph.json exists
cat .github/hooks/memory-graph.json

# Verify adapters are executable
chmod +x scripts/adapters/*.sh

# Check Copilot CLI has hooks support
copilot --version
# Requires Copilot CLI 1.30+

# Restart Copilot CLI
```

---

## See Also

- **Team knowledge:** `AGENTS.md` + `.agents/skills/` (conventions, workflows)
- **Cheat sheet:** `docs/cheat-sheet.md`
- **Main compass:** `.cursor/rules/main.mdc` (project context)
- **SDLC workflow:** `.cursor/rules/sdlc.mdc` (when to use ship-feature)
- **Copilot docs:** https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks

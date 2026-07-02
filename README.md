# memory-graph

Give any repo a persistent brain that survives agent sessions — without bloating every Cursor turn.

**Design goal:** persistent memory first, token savings second. The agent reads a slim brief + compressed state file, queries the code graph via subagents (not raw `graph.json`), and skips extra hook turns unless you opt in.

---

## What it does

| Layer | What | Token cost |
|-------|------|------------|
| **Brief** | `.cursor/rules/main.mdc` — purpose + god nodes table | ~small, always loaded |
| **Working memory** | `memory/state.yaml` — open items, context, blocked | Read on demand (~20 lines) |
| **Sessions** | `sessions/` + `memory.md` index | Written by hook, no followup turn |
| **Graph** | graphify → `graphify-out/` | Subagent scout per task, not inline |
| **Compression** | Structural (every stop) + semantic (opt-in) | Structural = free |

---

## Quick start

```bash
cd /your/project
curl -sL https://github.com/SundaraSwani/memory-graph/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1 && bash setup
/graphify .    # once — builds graph, populates god nodes in main.mdc
```

→ **[Cheat sheet](docs/cheat-sheet.md)** for commands, env vars, and troubleshooting.

`setup` installs hooks, rules, graphify, and the post-commit hook. **gstack is opt-in:** `INSTALL_GSTACK=1 bash setup`.

---

## How the session hook works

On every agent **stop** (when git-tracked files changed):

1. **Smart gate** — skip session file if fewer than 3 files changed and no god-node blast radius
2. **Session file** — structured YAML frontmatter only (no extra agent turn)
3. **Structural compress** — rollup → `memory/state.yaml`, archive prior days
4. **Semantic compress** — only if enabled and caps hit (see below)
5. **Graphify AST update** — background, no LLM (when code files changed)

**Never creates a session for:** pure Q&A, edits under `.cursor/`, `sessions/`, `memory.md`, `graphify-out/`.

```yaml
# sessions/2026-07-02-1.md — example
---
date: 2026-07-02
time: 14:32
session: 1
topics: "app/campaigns, app/signup"
scope:
  - app/campaigns.go
  - app/signup.go
god_nodes_touched: []
open: []
blocked: []
context: ""
facts: []
---
```

The agent may fill `context:` and `open:` **in the same turn** — one line each, not prose essays. Git diff covers *what* changed; memory covers *what's still open*.

---

## Memory tiers (structural compression)

Runs automatically on every file-changing stop and on `git commit`. **No LLM.**

| Tier | Location | Contents |
|------|----------|----------|
| **Hot** | `memory/state.yaml` | Merged `open`, `blocked`, `recent_context`, `god_nodes_recent` |
| **Warm** | `sessions/*.md` | Today's session files |
| **Cold** | `sessions/archive/YYYY-MM.yaml` | Prior days (archived daily by default) |
| **Index** | `memory.md` | Last 30 sessions (trimmed automatically) |

```bash
# Manual run
python3 .cursor/hooks/compress-memory.py

# Keep session files for 14 days instead of daily archive
MEMORY_ARCHIVE_MODE=age MEMORY_ARCHIVE_DAYS=14 python3 .cursor/hooks/compress-memory.py
```

When lists hit their caps (`open` ≥ 10, etc.), the hook writes `memory/.semantic-pending` — your signal to run semantic compression (below).

---

## Semantic compression (optional, per repo)

Structural merge is mechanical — it can't drop stale items or summarize. **Semantic compression** distills memory when caps are hit.

**Default: off.** Each git repo opts in independently. Other repos on your machine are unaffected.

### Option A — Local Ollama (recommended)

Uses your machine. **No Cursor agent tokens.**

**1. Install Ollama** (one-time, system-wide)

```bash
# https://ollama.com/download
ollama serve
ollama pull llama3.2:3b
```

**2. Enable for this repo**

```bash
bash scripts/enable-semantic-ollama.sh
```

Creates `.memory-graph/ollama.yaml` (gitignored). Example template is committed at `.memory-graph/ollama.example.yaml`.

**3. Verify**

```bash
bash scripts/check-ollama.sh
```

**What happens when enabled**

```
Structural caps hit → memory/.semantic-pending
    → hook calls semantic-compress-ollama.py
    → Ollama rewrites memory/state.yaml (≤15 lines)
    → clears pending, no Cursor followup
```

**Status files**

| File | Purpose |
|------|---------|
| `memory/.semantic-ollama-status` | Last run: ok / message |
| `memory/.semantic-ollama-last-error` | Why Ollama failed (server down, model missing, bad output) |

**Config** (`.memory-graph/ollama.yaml`)

```yaml
enabled: true
host: http://127.0.0.1:11434
model: llama3.2:3b          # must match: ollama pull <model>
max_archive_chars: 12000
timeout: 120
```

**Disable for this repo:** `enabled: false` in config, or `rm .memory-graph/ollama.yaml`.

---

### Option B — Cursor agent

Uses the `semantic-compress` skill via a one-time hook followup when caps hit. Costs agent tokens.

```bash
bash scripts/enable-semantic-auto.sh
```

Only use if you don't have Ollama. Don't enable both unless you want Ollama first with agent as fallback.

**Manual check**

```bash
python3 .cursor/hooks/compress-memory.py --check-semantic   # exit 2 if pending
```

---

### Which option should I use?

| | Ollama | Cursor agent |
|---|--------|--------------|
| **Cost** | Free (local GPU/CPU) | Cursor tokens |
| **Setup** | Install Ollama + enable script | One enable script |
| **Privacy** | Stays on your machine | Cloud model |
| **Quality** | Depends on model size | Usually higher |

---

## Graph traversal (graph scout)

Do **not** load `graphify-out/graph.json` into chat. Instead:

1. **Scout subagent** (every task) — returns ~500 token summary
2. **Drill subagent** (if HIGH/CRITICAL god node) — blast radius, callers

See `.cursor/rules/main.mdc` and `.agents/skills/graph-scout/SKILL.md`.

| Trigger | What runs | LLM? |
|---------|-----------|------|
| Agent stop (code changed) | graphify `--update` (AST) | No |
| `git commit` | graphify full rebuild | Only for new docs/images |
| Manual `/graphify .` | Full pipeline | Yes |

---

## What gets installed

| Path | Purpose |
|------|---------|
| `.cursor/rules/main.mdc` | Slim AI brief (always loaded) |
| `.cursor/rules/sdlc.mdc` | Opt-in workflow router (~50 lines) — points to `ship-feature` |
| `.cursor/hooks/on-session-end.sh` | Session + compress + optional Ollama |
| `.cursor/hooks/compress-memory.py` | Structural compression |
| `.cursor/hooks/semantic-compress-ollama.py` | Ollama semantic compression |
| `.memory-graph/ollama.example.yaml` | Ollama config template |
| `memory.md` + `sessions/` | Session index and files |
| `post-commit.sh` | graphify rebuild on commit |

---

## Testing

Sandbox tests use isolated `/tmp` dirs — no network, no LLM.

```bash
bash scripts/test.sh                    # full suite
bash scripts/test-static.sh             # fast syntax/contract checks
bash scripts/test-compress-sandbox.sh   # compression + hook gates
```

**memory-graph development only** — block push if tests fail:

```bash
bash scripts/install-dev-hooks.sh
git push   # runs tests automatically; use --no-verify to skip
```

---

## Optional: gstack + ship-feature

**End-to-end features:** **`ship-feature`** skill — [.agents/skills/ship-feature/SKILL.md](.agents/skills/ship-feature/SKILL.md). Slim router: [sdlc.mdc](.cursor/rules/sdlc.mdc).

**gstack** (optional extras):

```bash
INSTALL_GSTACK=1 bash setup
```

Adds `/spec`, `/review`, `/qa`, `/ship` when you need them outside the ship-feature loop.

---

## Requirements

- **Cursor** — hooks + `.mdc` rules
- **Python 3.8+** — graphify + compression scripts
- **Git**
- **Ollama** — only if using local semantic compression
- **Bun 1.0+** — only if using gstack browser features

---

## Docs

- **[Cheat sheet](docs/cheat-sheet.md)** — install, compress, Ollama, graph, tests, troubleshooting

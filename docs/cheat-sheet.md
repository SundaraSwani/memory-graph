# memory-graph cheat sheet

Quick reference. Full docs → [README](../README.md).

---

## Install

```bash
cd /your/project
curl -sL https://github.com/SundaraSwani/memory-graph/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=1 && bash setup
/graphify .                              # once — graph + god nodes in main.mdc
```

Optional gstack SDLC:

```bash
INSTALL_GSTACK=1 bash setup
```

Remote install (toolkit already cloned):

```bash
cd /your/project && ~/.cursor/skills/memory-graph/setup
```

Upgrade existing install (hooks, scripts, `.agents` only — keeps memory, sessions, config):

```bash
cd /your/project
bash memory-graph/scripts/upgrade-memory-graph.sh    # nested toolkit
# or
bash scripts/upgrade-memory-graph.sh               # after first upgrade
# dry run:
DRY_RUN=1 bash scripts/upgrade-memory-graph.sh
```

---

## Files the agent reads

| Read first | Path |
|------------|------|
| Brief (always loaded) | `.cursor/rules/main.mdc` |
| Working memory | `memory/state.yaml` |
| Session index | `memory.md` |
| Today's sessions | `sessions/*.md` |
| Full architecture | `graphify-out/GRAPH_REPORT.md` (via graph scout, not inline) |

---

## Session hook

| Situation | Session file? | Compress? |
|-----------|---------------|-------------|
| No file changes | No | No |
| `.cursor/` / `sessions/` / `memory.md` only | No | No |
| 1–2 files, no god node | No | Yes |
| 3+ files or god node hit | Yes | Yes |

### Change tracking (`MEMORY_TRACK`)

The hook learns what changed via **git diff** and/or a **Cursor edit ledger** (`.memory-graph/changed-files`, written by the `afterFileEdit` hook).

| Mode | Meaning |
|------|---------|
| **`auto`** *(default)* | **Cursor ledger only.** No session when the agent edited nothing (ignores dirty git tree). |
| **`git`** | **Git diff only.** Whole working tree — use only if you never rely on the edit ledger. |
| **`cursor`** | Same as `auto` (ledger only). Explicit for non-git folders. |

Set via env or `.memory-graph/config.yaml`:

```bash
# one-off
MEMORY_TRACK=cursor

# persistent (copy example first)
cp .memory-graph/config.example.yaml .memory-graph/config.yaml
# edit: track: cursor
```

Requires both hooks in `.cursor/hooks.json` — `afterFileEdit` (tracker) + `stop` (session end). `bash setup` installs them; merge manually if you already had a custom `hooks.json`.

Agent fills in same turn (optional — hook auto-fills from transcript when empty):

```yaml
context: "one line the next agent needs"
open:
  - "still-actionable item"
blocked:
  - "external blocker if any"
```

---

## Structural compression (automatic, no LLM)

Runs on every file-changing stop + `git commit`.

```bash
python3 .cursor/hooks/compress-memory.py              # manual
python3 .cursor/hooks/compress-memory.py --check-semantic   # exit 2 if semantic needed
```

| Env var | Default | Meaning |
|---------|---------|---------|
| `MEMORY_TRACK` | `auto` | `auto` / `git` / `cursor` — how the hook detects changed files |
| `MEMORY_ARCHIVE_MODE` | `daily` | `daily` = archive prior days; `age` = use days |
| `MEMORY_ARCHIVE_DAYS` | `14` | Used when `MEMORY_ARCHIVE_MODE=age` |
| `MEMORY_INDEX_KEEP` | `30` | Rows kept in `memory.md` |
| `MEMORY_OPEN_MAX` | `10` | Cap before semantic pending |
| `MEMORY_CONTEXT_MAX` | `5` | Context lines cap |
| `MEMORY_SEMANTIC_INTERVAL_DAYS` | `7` | Days between semantic prompts |

| Tier | Path |
|------|------|
| Hot | `memory/state.yaml` |
| Warm | `sessions/*.md` (today) |
| Cold | `sessions/archive/YYYY-MM.yaml` |
| Pending | `memory/.semantic-pending` |

---

## Semantic compression — Ollama (per repo, recommended)

**One-time (machine):**

```bash
# https://ollama.com/download
ollama serve
ollama pull llama3.2:3b
```

**Per repo:**

```bash
bash scripts/enable-semantic-ollama.sh    # creates .memory-graph/ollama.yaml
bash scripts/check-ollama.sh              # verify server + model
```

**Disable this repo:**

```bash
# edit .memory-graph/ollama.yaml → enabled: false
# or
rm .memory-graph/ollama.yaml
```

**Config** (`.memory-graph/ollama.yaml`, gitignored):

```yaml
enabled: true
host: http://127.0.0.1:11434
model: llama3.2:3b
max_archive_chars: 12000
timeout: 120
```

**Status:**

```bash
cat memory/.semantic-ollama-status       # last run ok/message
cat memory/.semantic-ollama-last-error   # if Ollama failed
```

**Manual run:**

```bash
python3 .cursor/hooks/semantic-compress-ollama.py --check
python3 .cursor/hooks/semantic-compress-ollama.py --dry-run
python3 .cursor/hooks/semantic-compress-ollama.py
```

---

## Semantic compression — Cursor agent (per repo, uses tokens)

```bash
bash scripts/enable-semantic-auto.sh     # hook followup → semantic-compress skill
rm .memory-graph-semantic-auto           # disable
```

Don't enable both Ollama and agent auto unless you want Ollama first, agent as fallback.

---

## Token savers (reduce Cursor usage)

```bash
bash scripts/enable-token-first.sh         # recommended — Ollama gateway, no scout auto-inject
bash scripts/enable-token-savers.sh        # agent brief + tool compress + scout on stop
bash scripts/enable-graph-scout-local.sh   # local graph scout (on demand)
```

| Feature | File | Saves |
|---------|------|-------|
| **Ollama gateway** | `memory/.cursor-context.yaml` | ~1200 chars at sessionStart; precomputed at stop |
| **Agent brief** | `memory/.agent-brief.yaml` | Fallback when gateway off |
| **sessionStart inject** | hook | Read-only — no LLM in the 10s window |
| **Tool compress** | `postToolUse` hook | Summarizes Shell/Grep/Read >6K chars |
| **Scout on stop** | hook | Off in token-first profile — run scout manually |

```bash
REPO_ROOT=. python3 .cursor/hooks/ollama-context-gateway.py --check
REPO_ROOT=. python3 .cursor/hooks/ollama-context-gateway.py --dry-run
REPO_ROOT=. python3 .cursor/hooks/ollama-context-gateway.py --force   # refresh cache
```

Disable in `.memory-graph/config.yaml`: `ollama_context_on_start: false`, `agent_brief: false`, `tool_output_compress: false`

---

## Graph

```bash
/graphify .                    # full build (LLM for docs/images)
/graphify update .             # AST only, fast
/graphify query "campaigns.go"  # CLI query (--budget 500)
```

**Local scout (optional, no subagent tokens):**

```bash
bash scripts/enable-graph-scout-local.sh
bash scripts/graph-scout-local.sh "files or concepts in scope"
cat memory/.graph-scout.yaml
bash scripts/check-graph-scout-local.sh
```

**Rule:** never load `graphify-out/graph.json` into main chat. Use local scout or graph-scout subagent fallback.

---

## Testing

```bash
bash scripts/test.sh                      # full suite
bash scripts/test-static.sh               # syntax + contracts
bash scripts/test-compress-sandbox.sh     # hook + compress sandbox

bash scripts/install-dev-hooks.sh         # pre-push gate (memory-graph dev)
git push                                  # runs tests; --no-verify to skip
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Ollama not reachable | `ollama serve` |
| Model not found | `ollama pull llama3.2:3b` (match `model` in config) |
| Semantic never runs | Check `memory/.semantic-pending` exists; caps may not be hit yet |
| Too many agent turns | Don't use `enable-semantic-auto.sh`; use Ollama instead |
| Sessions not created | Need 3+ **agent-edited** files or god-node hit; Q&A with dirty git tree is ignored |
| `state.yaml` stale | Runs every stop when files change; manual: `compress-memory.py` |

---

## One-liners

```bash
# Is semantic compression needed?
python3 .cursor/hooks/compress-memory.py --check-semantic

# Is Ollama configured and healthy?
bash scripts/check-ollama.sh

# What’s in working memory?
cat memory/state.yaml

# Recent session index
tail -10 memory.md
```

---

## ship-feature (end-to-end)

Use the **`ship-feature`** skill — full prompts in [.agents/skills/ship-feature/SKILL.md](../.agents/skills/ship-feature/SKILL.md). Router: [sdlc.mdc](../.cursor/rules/sdlc.mdc).

Drop your project's `ship-feature` skill under `.agents/skills/` or edit the shipped copy for your repo (paths, DDD rules, test roots).

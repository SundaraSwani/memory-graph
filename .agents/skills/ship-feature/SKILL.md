---
name: ship-feature
description: Full development loop for any feature or fix — grill, research, slice into changes, write spec-driven tests (before code), implement code in isolation, validate against tests, guard boundaries, review, commit per slice, and persist to memory. Use when the user says "build this", "implement X", "add feature", "fix and ship", or any end-to-end development request in this workspace.
---

# Ship Feature

**Sub-agents run per change slice across sequential waves.** Each sub-agent is its own isolated
Task invocation — never merge two agents into one. The parent agent coordinates, synthesises,
applies files, commits each slice, and writes memory.

**Test-first, isolated:** tests are written from the spec *before* any production code.
The Test agent and Code agent never see each other's output.

**Commit-per-slice:** shipping is a `git commit`, not a PR. `post-commit.sh` runs graphify
`--update` and memory compress after each slice commit.

```
Wave 0 (parent):    Grill — clarify with user before any agent fires
Wave 1 (1 agent):   [Research]        ← Opus 4.8  (uses grill answers as context)
Wave 1.5 (parent):  Slice fan-out — N change slices, each with its own briefs

Per slice (parallel if independent):
  Wave 2 (1 agent):   [Test]            ← Sonnet — spec only, NO production code context
  Wave 3 (1 agent):   [Code]            ← Sonnet — spec only, NO test file context
  Wave 4 (2 agents):  [Validate] ∥ [DDD Guard]  ← Sonnet (both) — Validate runs tests
  Wave 5 (2 agents):  [Comment] ∥ [Review]      ← Composer 2.5 / Opus 4.8
  Wave 5.5 (parent):  Commit slice      ← one commit per slice; post-commit hooks run

Wave 6 (parent):    Memory update
```

**Wave 0 (Grill) must complete before any sub-agent is launched.**
**Wave 1.5 (slice fan-out) must complete before any Wave 2 Test agent launches.**
Wave 2 (Test) must complete and parent must **apply test files** before Wave 3 (Code) for that slice.
Agents in the same wave launch in a **single message** (parallel Task calls).
Independent slices at the same wave may run in parallel; dependent slices run sequentially.

> **Customize per repo:** Edit paths, rules, and layer names in the wave prompts below.
> Default memory capture uses memory-graph (`memory/state.yaml`, `sessions/`).

---

## Isolation contract (non-negotiable)

| Agent | May receive | Must NOT receive |
|---|---|---|
| **Test** | Feature Brief, slice `<TEST SPEC>`, test root path, existing **test** helpers/patterns | Production source being changed, Code agent output, `<CODE BRIEF>`, implementation approach, other slices' specs |
| **Code** | Feature Brief, slice `<CODE BRIEF>`, architecture rules, file targets | Test file contents, Test agent output, assertion lists, `<TEST SPEC>` test scenarios, other slices' briefs |
| **Validate** | Both changed production files and test files for **this slice** | — (runs tests against code) |

Parent splits Wave 1 output into per-slice briefs — never pass Research findings wholesale to Test or Code.

---

## Wave 0 — Grill (parent, no sub-agent)

Before launching any agent, the parent runs a grill-me loop directly with the user.
**Do not launch Wave 1 until the grill is complete.**

### How to grill

- Ask questions **one at a time**. Do not list all questions upfront.
- For each question, provide your own recommended answer based on what you can see in the codebase or `memory/state.yaml` — let the user confirm, correct, or expand.
- If a question can be answered by reading the codebase yourself (a file path, a class name, an existing test), do it and skip asking.
- Stop grilling when you have a clear, unambiguous answer to every question below.

### Questions to work through (in order)

1. **Scope** — Which part of the system does this touch? Can you see evidence in the codebase that confirms this?
2. **Domain** — Which layer or module is the entry point for this change?
3. **Output** — What is the observable result when this feature is working? (API return shape, CLI output, config behavior, etc.)
4. **Edge cases** — What are the obvious ways this could go wrong? (null values, missing config, network failure, schema mismatch)
5. **Tests** — What scenarios must pass? List them as given/when/then or input → expected output. Do **not** discuss implementation.
6. **Constraints** — Hard constraints to respect? (frozen files, frozen branch, deploy config, backward compatibility)
7. **Definition of done** — How will you know the feature is finished? (specific test command green, query result, CLI output)

### When grilling is done

Summarise the answers into a **Feature Brief** (7 labelled bullets, one per question above).
This brief is injected into Wave 1 Research and used by the parent to build per-slice `<TEST SPEC>` and `<CODE BRIEF>`.

---

## Wave 1 — Research agent

**Subagent type:** `explore` (read-only)
**Model:** `claude-opus-4-8-thinking-high`

**Prompt:**

```
You are researching a feature before any code or tests are written.

Feature: <FEATURE>
Clarifications already gathered from the developer:
<GRILL ANSWERS>

Use the clarifications to focus your investigation. Answer each question with concrete
file paths and evidence — do not repeat what the grill answers already confirmed:

1. Which layers or modules are affected?
2. Which specific production files are most likely to change?
3. Where do tests for this area live? What helpers or patterns do existing tests use?
4. What does memory/state.yaml or memory.md say about open items in this area?
5. Which .cursor/rules/ files apply?

Return exactly 5 labelled bullets. Nothing else.
```

---

## Wave 1.5 — Slice fan-out (parent, no sub-agent)

After Wave 1 Research completes, parent decomposes work into **N Change Slices** before
launching any Test agent. Single-concern features may be one slice — fan-out is optional
when Research points to one file group with no independent seams.

### Slice rules

- **One slice = one independent concern** (one bug, one module, one config path, one test area).
- **No overlapping production files** across parallel slices.
- **Shared files or god nodes** → stack slices (finish and commit slice A before slice B starts Wave 2).
- **Name each slice** with a short slug (e.g. `config-passthrough`, `scout-local-tests`).

### How to decompose

1. List candidate slices from Research bullets 1–2 and Feature Brief scope.
2. Check independence: overlapping files, import chains, or god nodes → sequential, not parallel.
3. Per slice, record: slug, production files, test files, dependency on another slice (if any).
4. Per slice, build isolated briefs (see below).
5. Show the user a one-line plan per slice before launching Wave 2.

### Per-slice briefs (before Wave 2)

Merge Research output with the Feature Brief **per slice**:

**`<TEST SPEC>`** — for the Test agent only:
- Grill bullets: Output, Edge cases, Tests, Definition of done — scoped to this slice
- Research bullet 3 only (test root, helpers, naming patterns)
- Public API surface **as named in the grill** (function names, config keys, CLI flags) — behavior, not implementation
- Explicit test scenarios as a numbered list for this slice only

**`<CODE BRIEF>`** — for the Code agent only:
- Grill bullets: Scope, Domain, Output, Constraints — scoped to this slice
- Research bullets 1, 2, 4, 5 (layers, production files, memory context, rules) — filtered to this slice
- No test scenarios, no assertion wording, no test file paths

### Parallel vs sequential

| Situation | Launch |
|---|---|
| Slices share no files and no ordering dependency | All slices' Wave 2 agents in one message |
| Slice B depends on slice A's committed files | A runs Waves 2–5.5 (commit) before B starts Wave 2 |
| Single slice | Normal linear Waves 2–5.5 |

---

## Wave 2 — Test agent (spec-driven, before code)

**One agent per slice.** Do not launch Code in the same wave.
**Subagent type:** `generalPurpose`
**Model:** `claude-sonnet-5-thinking-medium`

**Prompt:**

```
You are writing tests BEFORE any production code exists for this feature slice.

Feature: <FEATURE>
Slice: <SLUG>
Behavior spec (your only source of truth):
<TEST SPEC>

Rules:
1. Write tests from the spec only — assert observable behavior, not implementation details.
2. Do NOT read production source files that will be created or changed (no peeking at the code under test).
3. You MAY read existing test files and helpers in the test root for patterns only.
4. Tests may fail until production code lands — that is expected (red phase).
5. Each test function has a one-line docstring stating what behavior it asserts.
6. Cover every numbered scenario in TEST SPEC plus edge cases from the spec.
7. Follow project test conventions from .cursor/rules/.
8. Touch only files listed in this slice's TEST SPEC.

Return all test files as full content. Label each file path clearly.
```

**After this agent completes:** parent applies all test files for this slice to disk. Do not show test contents to the Code agent.

---

## Wave 3 — Code agent (no test context)

**One agent per slice.** Launch only after Wave 2 test files for that slice are on disk.
**Subagent type:** `generalPurpose`
**Model:** `claude-sonnet-5-thinking-medium`

**Prompt:**

```
You are implementing a feature slice. Tests already exist on disk but you must NOT read them.

Feature: <FEATURE>
Slice: <SLUG>
Implementation brief (your only source of truth):
<CODE BRIEF>

Rules:
1. Do NOT open, read, or grep test files written for this feature slice.
2. Implement from the spec and architecture rules only.
3. Follow applicable .cursor/rules/ for this repo.
4. Comments explain WHAT the code does, not what changed.
5. Touch only production files listed in this slice's CODE BRIEF.
6. Return all changed production files as full content. Label each file path clearly.
```

**After this agent completes:** parent applies all production files for this slice to disk.

---

## Wave 4 — Validate agent ∥ DDD Guard agent

Launch both in a single message per slice after applying Wave 3 code for that slice.
**Validate model:** `claude-sonnet-5-thinking-medium` | **DDD Guard model:** `claude-4-sonnet`

### Validate agent prompt

```
You are validating a feature slice by running tests against production code.

Feature: <FEATURE>
Slice: <SLUG>
Changed production files: <LIST FROM CODE AGENT>
Test files: <LIST FROM TEST AGENT>

Run each check and report PASS / FAIL / SKIP:

1. IMPORT CHECK
   python -c "from <changed module> import <class>" — must not raise.

2. TEST RUN
   Run the project's test command (e.g. pytest or bash scripts/test.sh) — all green.
   If tests fail, quote the failing assertion and whether the bug is in code or test spec.

3. LINT
   ruff check <changed files> — zero errors (or project linter if different).

4. REPO-SPECIFIC CHECKS (only if applicable)
   dbt parse, sandbox scripts, integration smoke tests — run only what CODE BRIEF flagged.

For every FAIL: quote the exact error line and propose the minimal fix.
Parent fixes FAILs before Wave 5.
```

### DDD Guard agent prompt

```
You are a boundary enforcement specialist for this repo.

Slice: <SLUG>
Changed production files: <LIST FROM CODE AGENT>

Run every check defined in the project's .cursor/rules/ for layer isolation and
framework contamination. Adapt checks to this repo's architecture (edit this block per repo).

For Market_Tech example:
- domain/ — no I/O imports
- application/ — infrastructure only via ports
- infrastructure/ — side effects only here

Return a table: Check | Result | Evidence. Then a one-paragraph verdict.
```

---

## Wave 5 — Comment agent ∥ Review agent

Launch both in a single message per slice after Wave 4 is green for that slice.
**Comment model:** `composer-2.5-fast` | **Review model:** `claude-opus-4-8-thinking-high`

### Comment agent prompt

```
You are adding 1-liner inline comments to changed production code.

Slice: <SLUG>
Changed production files: <LIST FROM CODE AGENT>

Comment style:
- WHAT style: explain what the line or block does.
- One line per comment, no multi-line blocks.
- Never describe what changed — only what exists and why it matters.

Return each file in full with comments inserted inline.
```

### Review agent prompt

```
You are reviewing a feature slice along two axes. You may read both production and test files.

Feature: <FEATURE>
Slice: <SLUG>
Changed production files: <LIST FROM CODE AGENT>
Test files: <LIST FROM TEST AGENT>

AXIS 1 — Standards
Read applicable .cursor/rules/. For each violation: file path + line + rule broken.

AXIS 2 — Spec
Does the implementation satisfy the Feature Brief for this slice? Do tests cover the spec without testing implementation accidents?
List: (a) missing requirements, (b) scope creep, (c) tests that assert internals instead of behavior.

Format: two headings (## Standards, ## Spec). Under 300 words total.
End with: "Summary: N standards issues, M spec issues. Worst: <one line>."
```

**After this agent completes:** parent applies Comment output and fixes Review blockers before Wave 5.5.

---

## Wave 5.5 — Commit slice (parent, no sub-agent)

**Ship gate = one `git commit` per slice.** No PR step. Push only when the user asks.

After Wave 5 is green and all Review blockers are resolved for this slice:

1. **Stage named files only** — this slice's production + test files. Never `git add .` or `git add -A`.
2. **Commit** with a HEREDOC message:

```bash
git add <slice files only>
git commit -m "$(cat <<'EOF'
fix(memory-graph): passthrough all config keys in load_config

Slice: config-passthrough
EOF
)"
```

3. **`post-commit.sh` runs automatically** — graphify `--update` on changed files, then `compress-memory.py` rolls session → `memory/state.yaml`.
4. **Record the commit** in the parent's running log (slice slug → commit hash) for Wave 6.
5. **Dependent slices** — only start the next slice's Wave 2 after this commit lands.

### Commit rules

- **One slice = one commit** — do not batch unrelated slices.
- **No amend by default** — if Review found blockers after commit, make a new commit.
- **Amend only when** the user explicitly requests it, or a hook auto-modified files on the commit you just made.
- **Push is separate** — never push unless the user asks.

---

## Wave 6 — Memory (parent agent writes directly)

After all slices are committed and all FAILs are resolved:

### memory-graph (default)

1. Read today's session file in `sessions/` if the hook created one.
2. Append to frontmatter:
   - `context:` — one line on current project state after this feature (list committed slice slugs)
   - `open:` — only still-actionable follow-ups from Review / DDD Guard
3. Each slice commit already triggered `post-commit.sh` → `memory/state.yaml` is current.
4. Hook auto-compresses again on agent stop if there are uncommitted edits — no extra followup turn needed.

Keep YAML edits under ~10 lines. No prose essays — git log covers *what* changed per slice.

### Optional `.workshop/` layout (if your repo uses it)

**Session doc** — `.workshop/sessions/<SESSION_ID>_<slug>.md`

```markdown
## What happened
<2-4 bullets — one per committed slice>

## Decisions made
<one bullet per non-obvious choice>

## What to pick up next
<follow-ups, open risks, TODOs>
```

**MEMORY.md** — update `.workshop/MEMORY.md` current state + pick up next.

---

## Agent summary

| Wave | Agent | Type | Model | Parallel with | Isolation |
|---|---|---|---|---|---|
| 0 | Grill | parent (interactive) | — | — | — |
| 1 | Research | `explore` | `claude-opus-4-8-thinking-high` | — | read-only |
| 1.5 | Slice fan-out | parent | — | — | — |
| 2 | Test | `generalPurpose` | `claude-sonnet-5-thinking-medium` | other slices' Test (if independent) | no production code |
| 3 | Code | `generalPurpose` | `claude-sonnet-5-thinking-medium` | — (per slice, sequential) | no test files |
| 4 | Validate | `generalPurpose` | `claude-sonnet-5-thinking-medium` | DDD Guard | runs tests |
| 4 | DDD Guard | `generalPurpose` | `claude-4-sonnet` | Validate | production only |
| 5 | Comment | `generalPurpose` | `composer-2.5-fast` | Review | — |
| 5 | Review | `generalPurpose` | `claude-opus-4-8-thinking-high` | Comment | may read both |
| 5.5 | Commit slice | parent | — | — | — |
| 6 | Memory | parent | — | — | — |

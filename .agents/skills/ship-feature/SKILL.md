---
name: ship-feature
description: Full development loop for any feature or fix — research context, implement code, write tests, validate it runs, check DDD boundaries, apply 1-liner inline comments, review against standards, and persist decisions to memory. Use when the user says "build this", "implement X", "add feature", "fix and ship", or any end-to-end development request in this workspace.
---

# Ship Feature

**Seven separate sub-agents across four sequential waves.** Each sub-agent is its own isolated
Task invocation — never merge two agents into one. The parent agent coordinates, synthesises,
and writes memory.

```
Wave 0 (parent):    Grill — clarify with user before any agent fires
Wave 1 (1 agent):   [Research]        ← Opus 4.8  (uses grill answers as context)
Wave 2 (2 agents):  [Code] ∥ [Test]   ← Sonnet (both)
Wave 3 (2 agents):  [Validate] ∥ [DDD Guard]  ← Sonnet (both)
Wave 4 (2 agents):  [Comment] ∥ [Review]      ← Composer 2.5 / Opus 4.8
Wave 5 (parent):    Memory update
```

**Wave 0 (Grill) must complete before any sub-agent is launched.**
All agents in the same wave launch in a **single message** (parallel Task calls).

> **Customize per repo:** Edit paths, rules, and layer names in the wave prompts below.
> Default memory capture uses memory-graph (`memory/state.yaml`, `sessions/`).

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

1. **Scope** — Which part of the system does this touch? (competitor crawler, retailer crawler, dbt, infra, or multiple?) Can you see evidence in the codebase that confirms this?
2. **Domain** — Which DDD layer is the entry point for this change? (domain logic, application orchestration, or infrastructure side-effect?)
3. **Output** — What is the observable result when this feature is working? (new Snowflake column, new dbt model, different LLM extraction, CLI output, etc.)
4. **Edge cases** — What are the obvious ways this could go wrong or produce bad data? (null values, missing config, network failure, schema mismatch)
5. **Tests** — Do existing tests cover any part of this? What new test scenarios are needed?
6. **Constraints** — Are there any hard constraints to respect? (Snowflake column contract, deploy-infra values.yaml, an open PR, a frozen legacy file)
7. **Definition of done** — How will you know the feature is finished and correct? (specific query result, pytest green, crawl run output, dbt model row count)

### When grilling is done

Summarise the answers into a **Feature Brief** (7 labelled bullets, one per question above).
This brief is injected as `<GRILL ANSWERS>` into the Wave 1 Research agent prompt.

---

## Wave 1 — Research agent

**Subagent type:** `explore` (read-only)
**Model:** `claude-opus-4-8-thinking-high`

**Prompt:**

```
You are researching a feature in the Market_Tech codebase before any code is written.

Feature: <FEATURE>
Clarifications already gathered from the developer:
<GRILL ANSWERS>

Use the clarifications to focus your investigation. Answer each question with concrete
file paths and evidence — do not repeat what the grill answers already confirmed:

1. Which DDD layers are affected? (domain/, application/, infrastructure/, dbt, infra)
2. Which specific files are most likely to change? (grep class names, function names, table names)
3. Are there existing tests for this area? Where exactly?
4. What does memory/state.yaml or memory.md say about open items in this area?
5. Which .cursor/rules/ files apply?
   - crawler work → martech-ingestion-crawler.mdc
   - Python → python-coding-standards.mdc
   - dbt → martech-dbt-crawler.mdc

Return exactly 5 labelled bullets. Nothing else.
```

**After this agent completes:** merge its output with the Grill Answers into `<STAGE 1 FINDINGS>` and pass that to all Wave 2 agents.

---

## Wave 2 — Code agent ∥ Test agent

Launch both in a single message. Each is a separate `generalPurpose` subagent.
**Model (both):** `claude-4-sonnet`

### Code agent prompt

```
You are implementing a feature in Market_Tech.

Feature: <FEATURE>
Research context: <STAGE 1 FINDINGS>

Rules:
1. domain/ layer: pure Python only — NO I/O, NO Scrapy, NO Snowflake, NO Azure imports.
2. application/ layer: orchestrates domain + infrastructure via port interfaces only.
3. infrastructure/ layer: all side-effecting code (Snowflake, Scrapy, LLM) lives here.
4. Follow .cursor/rules/python-coding-standards.mdc — frozen dataclasses, type hints, no bare excepts.
5. Comments explain WHAT the code does (learning-phase style), not what changed.
6. Return all changed files as full content. Label each file path clearly.
```

### Test agent prompt

```
You are writing pytest tests for a feature in Market_Tech.

Feature: <FEATURE>
Research context: <STAGE 1 FINDINGS>
Test root: ingestions/crawler-ingestion/tests/ (create if absent)

Rules:
1. Domain tests: no mocks — pure-function assertions only.
2. Application tests: mock all ports with pytest-mock. No real Snowflake or Azure calls.
3. Infrastructure tests: fixture-based; stub all external calls.
4. Mirror module paths: tests/domain/competitor/test_<module>.py mirrors domain/competitor/<module>.py.
5. Each test function has a one-line docstring stating what it asserts.
6. Follow .cursor/rules/python-coding-standards.mdc.

Return all test files as full content. Label each file path clearly.
```

---

## Wave 3 — Validate agent ∥ DDD Guard agent

Launch both in a single message after applying Wave 2 code. Each is a separate `generalPurpose` subagent.
**Model (both):** `claude-4-sonnet`

### Validate agent prompt

```
You are validating a feature implementation in Market_Tech.

Feature: <FEATURE>
Changed files: <LIST FROM CODE AGENT>

Run each check and report PASS / FAIL / SKIP:

1. IMPORT CHECK
   python -c "from <changed module> import <class>" — must not raise.

2. TEST RUN
   pytest ingestions/crawler-ingestion/tests/ -q — all green.

3. LINT
   ruff check <changed files> — zero errors.

4. DBT PARSE (only if dbt files changed)
   dbt parse --profiles-dir martech-dbt/ --project-dir martech-dbt/

5. SNOWFLAKE SCHEMA (only if new columns added)
   Confirm new column names don't collide with or break staging models in
   martech-dbt/models/staging/competitor/ or martech-dbt/models/staging/retailer/.

6. MAKEFILE ENTRY POINT (only if a new run mode was added)
   Confirm a matching target exists in the root Makefile.

For every FAIL: quote the exact error line and propose the minimal fix.
```

### DDD Guard agent prompt

```
You are a DDD boundary enforcement specialist for Market_Tech.

The project uses strict layered DDD:
- domain/         — pure business logic. Entities, value objects, domain services.
- application/    — orchestration only. Calls domain via domain objects; calls infrastructure via ports.
- infrastructure/ — all side effects (Snowflake, Scrapy, Azure LLM, file I/O).

Changed files: <LIST FROM CODE AGENT>
Canonical crawler root: ingestions/crawler-ingestion/

Run every check below. Report PASS / FAIL for each. Be precise — quote the offending import or call.

1. DOMAIN ISOLATION
   - domain/ must contain zero imports from infrastructure/ or application/.
   - Grep: `grep -r "from.*infrastructure" ingestions/crawler-ingestion/domain/`
   - Grep: `grep -r "from.*application" ingestions/crawler-ingestion/domain/`
   - Both must return nothing.

2. APPLICATION LAYER PURITY
   - application/ must never import infrastructure modules directly.
   - It may only call infrastructure through port interfaces defined in application/ports/.
   - Grep: `grep -r "from.*infrastructure" ingestions/crawler-ingestion/application/`
   - Flag any direct infrastructure import that bypasses a port.

3. INFRASTRUCTURE ALLOWED IMPORTS
   - infrastructure/ may import from domain/ for value objects and entities (read-only).
   - Flag any import where infrastructure/ calls a domain service method that produces business logic.
   - Grep: `grep -r "from.*domain.*service" ingestions/crawler-ingestion/infrastructure/`

4. FRAMEWORK CONTAMINATION
   - Scrapy, snowflake-connector, openai, azure — must ONLY appear in infrastructure/.
   - Grep each across domain/ and application/. All must return nothing.

5. CIRCULAR IMPORTS
   - Does any domain module import from another module that imports back into domain/?
   - Trace the import chain for each changed domain file.

6. VALUE OBJECT CORRECTNESS
   - New value objects in domain/shared/ must be frozen dataclasses (not Pydantic BaseModel).
   - Check: domain/shared/models.py and any new shared model files.
   - Note: existing PricingDetails/PDPDetails are Pydantic (known debt) — flag new ones only.

Return a table: Check | Result | Evidence. Then a one-paragraph verdict: is the DDD boundary intact?
```

---

## Wave 4 — Comment agent ∥ Review agent

Launch both in a single message after Wave 3 is green. Each is a separate `generalPurpose` subagent.
**Comment model:** `composer-2.5-fast` | **Review model:** `claude-opus-4-8-thinking-high`

### Comment agent prompt

```
You are adding 1-liner inline comments to changed code in Market_Tech.

Changed files: <LIST FROM CODE AGENT>

Comment style for this workspace (developer is in learning phase):
- WHAT style: explain what the line or block does, not just repeat the code.
- One line per comment, no multi-line blocks.
- Never describe what changed — only what exists and why it matters.
- Prioritise: class purpose, method intent, non-obvious conditionals, magic values.

Bad:  # added error handling
Good: # guard: skip rows missing price to avoid null-propagation into Snowflake

Return each file in full with comments inserted inline.
```

### Review agent prompt

```
You are reviewing changed code in Market_Tech along two axes.

Feature: <FEATURE>
Changed files: <LIST FROM CODE AGENT>

AXIS 1 — Standards
Read .cursor/rules/python-coding-standards.mdc and .cursor/rules/martech-ingestion-crawler.mdc.
For each violation: file path + line number + the exact rule it breaks.

AXIS 2 — Spec
Does the implementation cover everything the feature description asked for?
List: (a) missing requirements, (b) scope creep, (c) wrong implementations.
Quote the feature description for each finding.

Format: two headings (## Standards, ## Spec). Under 300 words total.
End with: "Summary: N standards issues, M spec issues. Worst: <one line>."
```

---

## Wave 5 — Memory (parent agent writes directly)

After all agents complete and all FAILs are resolved:

### memory-graph (default)

1. Read today's session file in `sessions/` if the hook created one.
2. Append to frontmatter:
   - `context:` — one line on current project state after this feature
   - `open:` — only still-actionable follow-ups from Review / DDD Guard
3. Hook auto-compresses to `memory/state.yaml` on agent stop — no extra followup turn needed.

Keep YAML edits under ~10 lines. No prose essays — git diff covers *what* changed.

### Optional `.workshop/` layout (if your repo uses it)

**Session doc** — `.workshop/sessions/<SESSION_ID>_<slug>.md`

```markdown
## What happened
<2-4 bullets>

## Decisions made
<one bullet per non-obvious choice>

## What to pick up next
<follow-ups, open risks, TODOs>
```

**MEMORY.md** — update `.workshop/MEMORY.md` current state + pick up next.

---

## Agent summary

| Wave | Agent | Type | Model | Parallel with |
|---|---|---|---|---|
| 0 | Grill | parent (interactive) | — | — |
| 1 | Research | `explore` | `claude-opus-4-8-thinking-high` | — |
| 2 | Code | `generalPurpose` | `claude-4-sonnet` | Test |
| 2 | Test | `generalPurpose` | `claude-4-sonnet` | Code |
| 3 | Validate | `generalPurpose` | `claude-4-sonnet` | DDD Guard |
| 3 | DDD Guard | `generalPurpose` | `claude-4-sonnet` | Validate |
| 4 | Comment | `generalPurpose` | `composer-2.5-fast` | Review |
| 4 | Review | `generalPurpose` | `claude-opus-4-8-thinking-high` | Comment |
| 5 | Memory | parent | — | — |

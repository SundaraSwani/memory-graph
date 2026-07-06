---
name: grill-me
description: A relentless interview to sharpen a plan or design.
disable-model-invocation: true
---

Run a grilling session with the user before writing code or launching sub-agents.

### How to grill

- Ask questions **one at a time**. Do not list all questions upfront.
- For each question, provide your own recommended answer based on the codebase or `memory/.agent-brief.yaml` — let the user confirm, correct, or expand.
- If a question can be answered by reading the codebase yourself, do it and skip asking.
- Stop when you have a clear, unambiguous answer to every open question.

### When grilling is done

Summarise the answers into a short **Feature Brief** (labelled bullets). Reference existing artifacts by path instead of duplicating them.

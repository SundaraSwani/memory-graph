#!/usr/bin/env python3
"""Fill session frontmatter (context, open, blocked) from Cursor stop-hook transcript.

The stop hook creates the session file after the agent finishes, so agents rarely
fill context themselves. This script runs immediately after session creation.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

USER_TAG = re.compile(r"<user_query>\s*([\s\S]*?)\s*</user_query>", re.I)
TIMESTAMP_TAG = re.compile(r"<timestamp>[\s\S]*?</timestamp>", re.I)
REDACTED = re.compile(r"\[REDACTED\]", re.I)
OPEN_PATTERNS = (
    re.compile(r"(?im)^(?:[-*]\s+|\d+\.\s+)(.+)$"),
    re.compile(r"(?i)(?:still need to|need to fix|todo:?|next:?)\s+(.+?)(?:\.|$)"),
)
BLOCKED_PATTERNS = (
    re.compile(r"(?i)(?:blocked by|waiting on|waiting for|need approval for)\s+(.+?)(?:\.|$)"),
)


def repo_root() -> Path:
    root = os.environ.get("REPO_ROOT")
    return Path(root) if root else Path.cwd()


def load_ollama_config(root: Path) -> dict | None:
    path = root / ".memory-graph" / "ollama.yaml"
    if not path.is_file():
        return None
    cfg = {"enabled": False, "host": "http://127.0.0.1:11434", "model": "llama3.2:3b", "timeout": 60, "temperature": 0}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key == "enabled":
            cfg[key] = val.lower() in ("true", "yes", "1")
        elif key in ("host", "model"):
            cfg[key] = val
        elif key in ("timeout",):
            try:
                cfg[key] = int(val)
            except ValueError:
                pass
        elif key == "temperature":
            try:
                cfg[key] = float(val)
            except ValueError:
                pass
    return cfg if cfg.get("enabled") else None


def session_fill_enabled(root: Path) -> bool:
    cfg = root / ".memory-graph" / "config.yaml"
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.match(r"^session_fill_from_transcript:\s*false", line.strip()):
                return False
    if os.environ.get("MEMORY_SESSION_FILL", "1") == "0":
        return False
    return True


def parse_frontmatter(text: str) -> tuple[dict, str, str]:
    if not text.startswith("---"):
        return {}, text, ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text, ""
    fm = parts[1]
    body = parts[2] if len(parts) > 2 else ""
    data: dict = {}
    m = re.search(r'^context:\s*"(.*)"', fm, re.M)
    if m:
        data["context"] = m.group(1)
    for key in ("open", "blocked", "facts", "scope", "god_nodes_touched"):
        data[key] = _yaml_list(fm, key)
    for key in ("date", "time", "topics"):
        m = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
        if m:
            data[key] = m.group(1).strip().strip('"')
    m = re.search(r"^session:\s*(\d+)", fm, re.M)
    if m:
        data["session"] = m.group(1)
    return data, fm, body


def _yaml_list(body: str, key: str) -> list[str]:
    if re.search(rf"^{key}:\s*\[\]\s*$", body, re.M):
        return []
    block = re.search(rf"^{key}:\s*\n((?:  - .+\n?)*)", body, re.M)
    if not block:
        return []
    return [
        line.strip()[2:].strip().strip('"')
        for line in block.group(1).splitlines()
        if line.strip().startswith("- ")
    ]


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render_frontmatter(data: dict) -> str:
    lines = [
        "---",
        f"date: {data.get('date', '')}",
        f"time: {data.get('time', '')}",
        f"session: {data.get('session', '1')}",
        f'topics: "{data.get("topics", "")}"',
        "scope:",
    ]
    for item in data.get("scope") or []:
        lines.append(f"  - {item}")
    lines.append("god_nodes_touched:")
    god = data.get("god_nodes_touched") or []
    if not god:
        lines.append("  []")
    else:
        for item in god:
            lines.append(f"  - {item}")
    lines.append("open:")
    open_items = data.get("open") or []
    if not open_items:
        lines.append("  []")
    else:
        for item in open_items[:8]:
            lines.append(f'  - "{_escape(item)}"')
    lines.append("blocked:")
    blocked = data.get("blocked") or []
    if not blocked:
        lines.append("  []")
    else:
        for item in blocked[:5]:
            lines.append(f'  - "{_escape(item)}"')
    context = (data.get("context") or "").strip()
    lines.append(f'context: "{_escape(context)}"')
    facts = data.get("facts") or []
    if not facts:
        lines.append("facts: []")
    else:
        lines.append("facts:")
        for item in facts:
            lines.append(f"  - {item}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _clean_user_text(text: str) -> str:
    text = TIMESTAMP_TAG.sub("", text)
    m = USER_TAG.search(text)
    if m:
        text = m.group(1)
    text = re.sub(r"</?[a-z_]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1200]


def _clean_assistant_text(text: str) -> str:
    text = REDACTED.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_transcript(path: Path) -> tuple[list[str], list[str]]:
    users: list[str] = []
    assistants: list[str] = []
    if not path.is_file():
        return users, assistants
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = row.get("role")
        msg = row.get("message") or {}
        parts = msg.get("content") or []
        texts: list[str] = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                t = (part.get("text") or "").strip()
                if t:
                    texts.append(t)
        blob = "\n".join(texts).strip()
        if not blob:
            continue
        if role == "user":
            cleaned = _clean_user_text(blob)
            if cleaned:
                users.append(cleaned)
        elif role == "assistant":
            cleaned = _clean_assistant_text(blob)
            if len(cleaned) > 40:
                assistants.append(cleaned)
    return users, assistants


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        norm = item.strip()
        if not norm or len(norm) < 4 or norm in seen:
            continue
        seen.add(norm)
        out.append(norm[:200])
    return out


def rules_fill(users: list[str], assistants: list[str], scope: list[str]) -> dict:
    context = ""
    if assistants:
        last = assistants[-1]
        # Prefer summary-like opening over tool chatter
        for para in re.split(r"(?<=[.!?])\s+", last):
            para = para.strip()
            if len(para) >= 30 and not para.lower().startswith("investigating"):
                context = para[:240]
                break
        if not context:
            context = last[:240]
    elif users:
        context = f"User: {users[-1][:200]}"

    if scope and context:
        base = Path(scope[0]).name if scope else ""
        if len(scope) <= 8:
            scope_hint = ", ".join(Path(s).name for s in scope[:5])
            context = f"{context} (files: {scope_hint})"
        elif base:
            context = f"{context} ({len(scope)} files incl. {base})"

    open_items: list[str] = []
    blocked_items: list[str] = []
    scan = "\n".join(assistants[-2:] + users[-1:])
    for pat in OPEN_PATTERNS:
        for m in pat.finditer(scan):
            item = m.group(1).strip().strip('"')
            if 4 < len(item) < 180:
                open_items.append(item)
    for pat in BLOCKED_PATTERNS:
        for m in pat.finditer(scan):
            item = m.group(1).strip().strip('"')
            if 4 < len(item) < 180:
                blocked_items.append(item)

    return {
        "context": context[:240],
        "open": _dedupe(open_items)[:8],
        "blocked": _dedupe(blocked_items)[:5],
    }


OLLAMA_SYSTEM = """You extract session memory from a coding-agent chat transcript.

Reply with ONLY valid YAML — no fences, no prose.

Required keys:
context: "one line summary for the next agent"
open:
  - "actionable follow-up (0-5 items)"
blocked:
  - "blocker if any (0-3 items, else empty list)"

Rules:
- Do not invent work not discussed in the transcript
- context must be one line, under 200 characters
- open items must be concrete next steps still outstanding
- blocked only for explicit blockers (approvals, missing deps, external waits)
"""


def ollama_fill(cfg: dict, users: list[str], assistants: list[str], scope: list[str]) -> dict | None:
    user_blob = "\n".join(f"USER: {u}" for u in users[-3:])
    asst_blob = "\n".join(f"ASSISTANT: {a[:800]}" for a in assistants[-3:])
    scope_blob = "\n".join(f"- {s}" for s in scope[:20])
    prompt = (
        "Extract session memory from this chat.\n\n"
        f"SCOPE FILES:\n{scope_blob or '(none)'}\n\n"
        f"{user_blob}\n\n{asst_blob}"
    )
    url = cfg["host"].rstrip("/") + "/api/chat"
    body = json.dumps(
        {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": OLLAMA_SYSTEM},
                {"role": "user", "content": prompt[:6000]},
            ],
            "stream": False,
            "options": {"temperature": float(cfg.get("temperature", 0))},
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=int(cfg.get("timeout", 60))) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    text = ((raw.get("message") or {}).get("content") or "").strip()
    m = re.search(r'^context:\s*"(.*)"', text, re.M)
    if not m:
        return None
    context = m.group(1).strip()
    open_items = _yaml_list(text, "open")
    blocked_items = _yaml_list(text, "blocked")
    if not context:
        return None
    return {
        "context": context[:240],
        "open": _dedupe(open_items)[:8],
        "blocked": _dedupe(blocked_items)[:5],
    }


def fill_session(session_path: Path, transcript_path: Path) -> bool:
    root = repo_root()
    if not session_fill_enabled(root):
        return False

    text = session_path.read_text(encoding="utf-8", errors="replace")
    data, _, body = parse_frontmatter(text)
    if (data.get("context") or "").strip():
        return False

    users, assistants = parse_transcript(transcript_path)
    if not users and not assistants:
        return False

    scope = data.get("scope") or []
    filled = rules_fill(users, assistants, scope)

    ollama_cfg = load_ollama_config(root)
    if ollama_cfg:
        ollama_result = ollama_fill(ollama_cfg, users, assistants, scope)
        if ollama_result:
            filled = ollama_result

    if not (filled.get("context") or "").strip():
        return False

    data["context"] = filled["context"]
    if filled.get("open") and not data.get("open"):
        data["open"] = filled["open"]
    if filled.get("blocked") and not data.get("blocked"):
        data["blocked"] = filled["blocked"]

    session_path.write_text(render_frontmatter(data) + body.lstrip("\n"), encoding="utf-8")
    return True


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: fill-session-from-transcript.py <session.md> <transcript.jsonl>", file=sys.stderr)
        return 1
    session_path = Path(sys.argv[1])
    transcript_path = Path(sys.argv[2])
    if not session_path.is_file():
        return 0
    if fill_session(session_path, transcript_path):
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

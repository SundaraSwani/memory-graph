#!/usr/bin/env python3
"""Ollama context gateway — distill memory for sessionStart injection.

Precomputed at session stop (on-session-end.sh). sessionStart only reads the
cached file so the 10s hook budget is never spent on network I/O.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REPO = {
    "ollama_context_on_start": False,
    "ollama_context_max_lines": 15,
    "ollama_context_cache_mins": 30,
    "ollama_context_max_chars": 1200,
}

DEFAULT_OLLAMA = {
    "enabled": False,
    "host": "http://127.0.0.1:11434",
    "model": "llama3.2:3b",
    "max_archive_chars": 6000,
    "max_archive_files": 2,
    "timeout": 60,
    "temperature": 0,
}

CONTEXT_SYSTEM = """You distill project memory for a coding agent's session start.

CRITICAL: Reply with ONLY valid YAML. No markdown fences, no prose.

Rules:
- Max {max_lines} lines of YAML (comments with # allowed)
- Focus: current project state, open tasks, blockers
- Drop stale/resolved items; do not invent facts
- No file lists, no graph scout, no scope paths

Required shape:
updated: YYYY-MM-DD
open:
  - "actionable item"
blocked: []
recent:
  - "one line on current focus"
"""


def repo_root() -> Path:
    root = os.environ.get("REPO_ROOT")
    return Path(root) if root else Path.cwd()


def _load_semantic_module():
    path = Path(__file__).resolve().parent / "semantic-compress-ollama.py"
    spec = importlib.util.spec_from_file_location("semantic_ollama", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_repo_config(root: Path) -> dict:
    cfg = dict(DEFAULT_REPO)
    path = root / ".memory-graph" / "config.yaml"
    if not path.is_file():
        return cfg
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key == "ollama_context_on_start":
            cfg[key] = val.lower() in ("true", "yes", "1")
        elif key in (
            "ollama_context_max_lines",
            "ollama_context_cache_mins",
            "ollama_context_max_chars",
        ):
            try:
                cfg[key] = int(val)
            except ValueError:
                pass
    return cfg


def load_ollama_config(root: Path) -> dict | None:
    path = root / ".memory-graph" / "ollama.yaml"
    if not path.is_file():
        return None
    cfg = dict(DEFAULT_OLLAMA)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key == "enabled":
            cfg[key] = val.lower() in ("true", "yes", "1")
        elif key in ("max_archive_chars", "timeout", "max_archive_files"):
            try:
                cfg[key] = int(val)
            except ValueError:
                pass
        elif key == "temperature":
            try:
                cfg[key] = float(val)
            except ValueError:
                pass
        elif key in ("host", "model"):
            cfg[key] = val
    return cfg if cfg.get("enabled") else None


def write_status(root: Path, ok: bool, message: str) -> None:
    mem = root / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    path = mem / ".cursor-context-status"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"ok: {'true' if ok else 'false'}",
        f"updated: {ts}",
        f"message: \"{message.replace(chr(34), chr(39))}\"",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _meta_path(root: Path) -> Path:
    return root / "memory" / ".cursor-context-meta"


def _context_path(root: Path) -> Path:
    return root / "memory" / ".cursor-context.yaml"


def cache_fresh(root: Path, cache_mins: int) -> bool:
    meta = _meta_path(root)
    if not meta.is_file() or not _context_path(root).is_file():
        return False
    for line in meta.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("generated_at:"):
            raw = line.split(":", 1)[1].strip()
            try:
                ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                age = time.time() - ts.timestamp()
                return age < cache_mins * 60
            except ValueError:
                return False
    return False


def write_meta(root: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _meta_path(root).write_text(f"generated_at: {ts}\n", encoding="utf-8")


def extract_yaml(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:yaml)?\s*\n([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    m = re.search(r"(?m)^(updated:|#)", text)
    if m and m.start() > 0:
        text = text[m.start() :].strip()
    return text


def validate_context(yaml_text: str) -> bool:
    return bool(re.search(r"^updated:\s*\S+", yaml_text, re.M)) and (
        "recent:" in yaml_text or "open:" in yaml_text
    )


def trim_lines(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text.strip() + "\n"
    kept = lines[:max_lines]
    kept.append(f"# ... ({len(lines) - max_lines} lines truncated)")
    return "\n".join(kept) + "\n"


def fallback_from_state(root: Path, max_lines: int) -> str:
    state = root / "memory" / "state.yaml"
    if not state.is_file():
        return ""
    text = state.read_text(encoding="utf-8", errors="replace")
    lines = []
    for line in text.splitlines():
        if line.startswith("# Auto-generated"):
            continue
        lines.append(line)
    body = trim_lines("\n".join(lines).strip(), max_lines)
    if not body.strip():
        return ""
    header = (
        "# Auto-generated fallback from memory/state.yaml — Ollama gateway unavailable.\n"
        "# Full history → sessions/archive/\n"
    )
    return header + body


def gather_source(root: Path, max_archive_chars: int, max_archive_files: int) -> str:
    sem = _load_semantic_module()
    return sem.gather_source(root, max_archive_chars, max_archive_files)


def build_user_message(source: str, max_lines: int) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return (
        f"Distill the following into a session-start context (max {max_lines} YAML lines). "
        f"Set updated to {today}.\n\nSOURCE:\n{source}"
    )


def run(root: Path, dry_run: bool = False, force: bool = False) -> int:
    repo_cfg = load_repo_config(root)
    if not repo_cfg.get("ollama_context_on_start"):
        write_status(root, True, "disabled (ollama_context_on_start: false)")
        return 0

    max_lines = int(repo_cfg.get("ollama_context_max_lines") or 15)
    cache_mins = int(repo_cfg.get("ollama_context_cache_mins") or 30)

    if not force and cache_fresh(root, cache_mins):
        write_status(root, True, "cache fresh — skipped Ollama call")
        return 0

    ollama_cfg = load_ollama_config(root)
    source = gather_source(
        root,
        int((ollama_cfg or DEFAULT_OLLAMA)["max_archive_chars"]),
        int((ollama_cfg or DEFAULT_OLLAMA).get("max_archive_files") or 2),
    )

    if dry_run:
        system = CONTEXT_SYSTEM.format(max_lines=max_lines)
        user = build_user_message(source, max_lines)
        print(f"--- system ({len(system)} chars) ---\n{system[:600]}\n")
        print(f"--- user ({len(user)} chars) ---\n{user[:2000]}" + ("\n..." if len(user) > 2000 else ""))
        return 0

    if not ollama_cfg:
        fb = fallback_from_state(root, max_lines)
        if fb:
            _context_path(root).write_text(fb, encoding="utf-8")
            write_meta(root)
            write_status(root, True, "fallback from state.yaml (Ollama not enabled)")
            return 0
        write_status(root, False, "Ollama not enabled and no state.yaml")
        return 1

    sem = _load_semantic_module()
    system = CONTEXT_SYSTEM.format(max_lines=max_lines)
    user = build_user_message(source, max_lines)

    try:
        raw = sem.ollama_chat(
            ollama_cfg["host"],
            ollama_cfg["model"],
            system,
            user,
            int(ollama_cfg["timeout"]),
            float(ollama_cfg.get("temperature", 0)),
        )
    except urllib.error.URLError as exc:
        fb = fallback_from_state(root, max_lines)
        if fb:
            _context_path(root).write_text(fb, encoding="utf-8")
            write_meta(root)
            write_status(root, True, f"fallback from state.yaml ({exc})")
            return 0
        write_status(root, False, f"Ollama unreachable: {exc}")
        return 2

    yaml_out = extract_yaml(raw)
    if not validate_context(yaml_out):
        fb = fallback_from_state(root, max_lines)
        if fb:
            _context_path(root).write_text(fb, encoding="utf-8")
            write_meta(root)
            write_status(root, True, "fallback from state.yaml (invalid Ollama output)")
            return 0
        write_status(root, False, "Ollama response was not valid context YAML")
        return 3

    header = (
        "# Auto-generated by ollama-context-gateway.py — injected at sessionStart only.\n"
        "# Full history → sessions/archive/\n"
    )
    out = header + trim_lines(yaml_out.strip(), max_lines)
    _context_path(root).write_text(out, encoding="utf-8")
    write_meta(root)
    write_status(root, True, f"gateway via ollama/{ollama_cfg['model']}")
    return 0


def main() -> int:
    root = repo_root()
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        repo_cfg = load_repo_config(root)
        print(f"ollama_context_on_start: {bool(repo_cfg.get('ollama_context_on_start'))}")
        print(f"  cache_mins: {repo_cfg.get('ollama_context_cache_mins', 30)}")
        print(f"  context file: {'ok' if _context_path(root).is_file() else 'missing'}")
        return 0

    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        return run(root, dry_run=True, force=True)

    force = len(sys.argv) > 1 and sys.argv[1] == "--force"
    return run(root, dry_run=False, force=force)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Semantic memory compression via local Ollama (optional per-repo).

Reads .memory-graph/ollama.yaml when enabled: true.
Triggered by on-session-end.sh when memory/.semantic-pending exists.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

DEFAULT_CONFIG = {
    "enabled": False,
    "host": "http://127.0.0.1:11434",
    "model": "llama3.2:3b",
    "max_archive_chars": 12000,
    "timeout": 120,
}


def repo_root() -> Path:
    root = os.environ.get("REPO_ROOT")
    return Path(root) if root else Path.cwd()


def load_config(root: Path) -> dict | None:
    path = root / ".memory-graph" / "ollama.yaml"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    cfg = dict(DEFAULT_CONFIG)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key in ("enabled",):
            cfg[key] = val.lower() in ("true", "yes", "1")
        elif key in ("max_archive_chars", "timeout"):
            try:
                cfg[key] = int(val)
            except ValueError:
                pass
        elif key in ("host", "model"):
            cfg[key] = val
    return cfg if cfg.get("enabled") else None


def write_status(root: Path, ok: bool, message: str) -> None:
    mem = root / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    path = mem / ".semantic-ollama-status"
    lines = [
        f"ok: {'true' if ok else 'false'}",
        f"date: {date.today().isoformat()}",
        f"message: \"{message.replace(chr(34), chr(39))}\"",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    err_path = mem / ".semantic-ollama-last-error"
    if ok:
        err_path.unlink(missing_ok=True)
    else:
        err_path.write_text(message + "\n", encoding="utf-8")


def gather_source(root: Path, max_archive_chars: int) -> str:
    parts: list[str] = []
    state = root / "memory" / "state.yaml"
    if state.is_file():
        parts.append("=== memory/state.yaml ===\n" + state.read_text(encoding="utf-8", errors="replace"))

    pending = root / "memory" / ".semantic-pending"
    if pending.is_file():
        parts.append("=== memory/.semantic-pending ===\n" + pending.read_text(encoding="utf-8", errors="replace"))

    archive_dir = root / "sessions" / "archive"
    if archive_dir.is_dir():
        budget = max_archive_chars
        chunks: list[str] = []
        for path in sorted(archive_dir.glob("*.yaml"), reverse=True):
            if budget <= 0:
                break
            text = path.read_text(encoding="utf-8", errors="replace")
            if len(text) > budget:
                text = text[:budget] + "\n... [truncated]"
            chunks.append(f"=== {path.name} ===\n{text}")
            budget -= len(text)
        if chunks:
            parts.append("=== sessions/archive/ ===\n" + "\n\n".join(chunks))

    sessions = sorted((root / "sessions").glob("*.md"), reverse=True)[:5]
    if sessions:
        today_parts = []
        for p in sessions:
            today_parts.append(f"--- {p.name} ---\n" + p.read_text(encoding="utf-8", errors="replace")[:2000])
        parts.append("=== sessions/ (today) ===\n" + "\n\n".join(today_parts))

    return "\n\n".join(parts)


def build_prompt(source: str) -> str:
    return f"""You compress project memory for a coding agent. Output ONLY valid YAML — no markdown fences, no explanation.

Rules:
- Max 15 lines of YAML fields (comments allowed with #)
- Merge duplicate open items; drop resolved/stale items
- Keep god node names if still relevant
- recent_context: one concise line on current project state
- Do not invent facts not in the source

Required shape:
updated: {date.today().isoformat()}
sessions_active: <number or 0>
open:
  - "item"
blocked: []
god_nodes_recent: []
recent_context:
  - "one line summary"

SOURCE:
{source}
"""


def ollama_generate(host: str, model: str, prompt: str, timeout: int) -> str:
    url = host.rstrip("/") + "/api/generate"
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data.get("response") or "").strip()


def extract_yaml(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:yaml)?\s*\n([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    # Drop leading prose before first key:
    m = re.search(r"(?m)^(updated:|#)", text)
    if m and m.start() > 0:
        text = text[m.start() :].strip()
    return text


def validate_output(yaml_text: str) -> bool:
    return bool(re.search(r"^updated:\s*\S+", yaml_text, re.M)) and "open:" in yaml_text


def run(root: Path, dry_run: bool = False) -> int:
    cfg = load_config(root)
    if not cfg:
        print("Ollama semantic compress not enabled for this repo.", file=sys.stderr)
        print("Run: bash scripts/enable-semantic-ollama.sh", file=sys.stderr)
        return 1

    pending = root / "memory" / ".semantic-pending"
    if not pending.is_file():
        write_status(root, True, "nothing pending")
        return 0

    source = gather_source(root, int(cfg["max_archive_chars"]))
    prompt = build_prompt(source)

    if dry_run:
        print(prompt[:2000] + ("\n..." if len(prompt) > 2000 else ""))
        return 0

    try:
        raw = ollama_generate(cfg["host"], cfg["model"], prompt, int(cfg["timeout"]))
    except urllib.error.URLError as e:
        msg = f"Ollama unreachable at {cfg['host']}: {e}. Is Ollama running? (ollama serve)"
        write_status(root, False, msg)
        print(msg, file=sys.stderr)
        return 2

    yaml_out = extract_yaml(raw)
    if not validate_output(yaml_out):
        msg = "Ollama response was not valid state.yaml — try a larger model or run semantic-compress skill"
        write_status(root, False, msg)
        print(msg, file=sys.stderr)
        print("--- raw response ---", file=sys.stderr)
        print(raw[:1500], file=sys.stderr)
        return 3

    header = (
        "# Auto-generated by semantic-compress-ollama.py — distilled working memory.\n"
        "# Full history → sessions/archive/\n"
    )
    (root / "memory" / "state.yaml").write_text(header + yaml_out.strip() + "\n", encoding="utf-8")
    pending.unlink(missing_ok=True)
    (root / "memory" / ".semantic-last-run").write_text(date.today().isoformat() + "\n", encoding="utf-8")
    write_status(root, True, f"compressed via ollama/{cfg['model']}")
    return 0


def check_ollama(host: str, model: str, timeout: int = 5) -> tuple[bool, str]:
    try:
        url = host.rstrip("/") + "/api/tags"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = {m.get("name", "") for m in data.get("models", [])}
        # Ollama may report "llama3.2:3b" or with latest suffix
        if model in names or any(n.startswith(model.split(":")[0]) for n in names):
            return True, f"Ollama OK — model available ({model})"
        return False, f"Ollama running but model '{model}' not found. Run: ollama pull {model}"
    except urllib.error.URLError as e:
        return False, f"Ollama not reachable at {host}: {e}"


def main() -> int:
    root = repo_root()
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        cfg = load_config(root)
        if not cfg:
            example = root / ".memory-graph" / "ollama.example.yaml"
            if example.is_file():
                print("Ollama not enabled. Run: bash scripts/enable-semantic-ollama.sh")
            else:
                print("No .memory-graph/ollama.yaml — optional per-repo feature.")
            return 1
        ok, msg = check_ollama(cfg["host"], cfg["model"])
        print(msg)
        return 0 if ok else 2

    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        cfg = load_config(root)
        if not cfg:
            print("Enable Ollama first: bash scripts/enable-semantic-ollama.sh", file=sys.stderr)
            return 1
        return run(root, dry_run=True)

    return run(root, dry_run=False)


if __name__ == "__main__":
    sys.exit(main())

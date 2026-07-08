"""Shared helpers for memory-graph hook unit tests."""

from __future__ import annotations

import importlib.util
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".cursor" / "hooks"


def load_hook(name: str):
    """Load a hook module from .cursor/hooks/<name>.py by file path."""
    path = HOOKS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load hook: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def sandbox_repo():
    """Temporary repo root with REPO_ROOT set for hook scripts."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".memory-graph").mkdir(parents=True)
        (root / "memory").mkdir(parents=True)
        (root / "sessions").mkdir(parents=True)
        old = os.environ.get("REPO_ROOT")
        os.environ["REPO_ROOT"] = str(root)
        try:
            yield root
        finally:
            if old is None:
                os.environ.pop("REPO_ROOT", None)
            else:
                os.environ["REPO_ROOT"] = old


def write_config(root: Path, content: str) -> Path:
    path = root / ".memory-graph" / "config.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def session_md(
    date: str,
    session: int = 1,
    *,
    context: str = "",
    open_items: list[str] | None = None,
    body: str = "",
) -> str:
    open_items = open_items or []
    open_block = "open:\n  []" if not open_items else "open:\n" + "\n".join(
        f'  - "{item}"' for item in open_items
    )
    return f"""---
date: {date}
session: {session}
{open_block}
blocked: []
context: "{context}"
god_nodes_touched: []
scope: []
facts: []
---
{body}
"""

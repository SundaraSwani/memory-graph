#!/usr/bin/env python3
"""Tests for Memory Observatory scanner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scan import discover_repos, is_memory_repo, scan_all, scan_repo


class ObservatoryScanTests(unittest.TestCase):
    def test_is_memory_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(is_memory_repo(root))
            (root / ".memory-graph").mkdir()
            self.assertTrue(is_memory_repo(root))

    def test_scan_repo_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "demo-project"
            root.mkdir()
            (root / ".memory-graph").mkdir()
            mem = root / "memory"
            mem.mkdir()
            (mem / "state.yaml").write_text(
                "updated: 2026-07-06\nsessions_active: 1\nrecent_context:\n  - demo context\n",
                encoding="utf-8",
            )
            sess = root / "sessions"
            sess.mkdir()
            (sess / "2026-07-06-1.md").write_text(
                '---\ndate: 2026-07-06\ntime: 12:00\nsession: 1\ncontext: "hello"\nscope:\n  - a.py\n---\n',
                encoding="utf-8",
            )
            (root / "memory.md").write_text(
                "| Date/Time | Session | Topics | Files | Session File |\n"
                "| 2026-07-06 12:00 | 1 | a.py | 1 files | [view](sessions/2026-07-06-1.md) |\n",
                encoding="utf-8",
            )
            m = scan_repo(root)
            self.assertEqual(m.sessions_today, 1)
            self.assertGreater(m.hot_bytes, 0)
            self.assertIn("demo context", m.recent_context)

    def test_discover_finds_nested_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            nested = base / "work" / "my-app"
            nested.mkdir(parents=True)
            (nested / "memory" / "state.yaml").parent.mkdir(parents=True)
            (nested / "memory" / "state.yaml").write_text("updated: 2026-07-06\n", encoding="utf-8")
            found = discover_repos([base], max_depth=4)
            self.assertTrue(any(p.name == "my-app" for p in found))

    def test_scan_all_json_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "only-repo"
            root.mkdir()
            (root / ".memory-graph").mkdir()
            (root / "memory").mkdir()
            (root / "memory" / "state.yaml").write_text("updated: 2026-07-06\n", encoding="utf-8")
            data = scan_all([root])
            self.assertGreaterEqual(data["summary"]["repos"], 1)
            self.assertTrue(data["repos"])


if __name__ == "__main__":
    unittest.main()

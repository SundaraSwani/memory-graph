"""Unit tests for fill-session-from-transcript.py."""

from __future__ import annotations

import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.helpers import load_hook, sandbox_repo, write_config

fill = load_hook("fill-session-from-transcript")

TRANSCRIPT_FIXTURE = [
    {
        "role": "user",
        "message": {
            "content": [
                {
                    "type": "text",
                    "text": "<timestamp>Wed</timestamp><user_query>Fix discount HTML pytest fixtures</user_query>",
                }
            ]
        },
    },
    {
        "role": "assistant",
        "message": {
            "content": [
                {
                    "type": "text",
                    "text": "Updated three discount fixture cases. Still need to fix the remaining failing assertions in test_html.py.",
                }
            ]
        },
    },
]

SESSION_TEMPLATE = """---
date: 2026-07-08
time: 12:00
session: 1
topics: "tests"
scope:
  - src/tests/test_html.py
  - src/tests/fixture_a.py
god_nodes_touched: []
open: []
blocked: []
context: ""
facts: []
---
"""


class TestParseTranscript(unittest.TestCase):
    def test_extracts_user_and_assistant(self):
        with sandbox_repo() as root:
            path = root / "transcript.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in TRANSCRIPT_FIXTURE), encoding="utf-8")
            users, assistants = fill.parse_transcript(path)
        self.assertEqual(len(users), 1)
        self.assertIn("Fix discount HTML", users[0])
        self.assertEqual(len(assistants), 1)
        self.assertIn("Updated three discount", assistants[0])

    def test_skips_invalid_json_lines(self):
        with sandbox_repo() as root:
            path = root / "transcript.jsonl"
            path.write_text("not json\n" + json.dumps(TRANSCRIPT_FIXTURE[0]) + "\n", encoding="utf-8")
            users, _ = fill.parse_transcript(path)
        self.assertEqual(len(users), 1)


class TestCleanUserText(unittest.TestCase):
    def test_strips_tags(self):
        raw = "<timestamp>Wed</timestamp><user_query>Hello world</user_query>"
        cleaned = fill._clean_user_text(raw)
        self.assertEqual(cleaned, "Hello world")
        self.assertNotIn("<user_query>", cleaned)


class TestRulesFill(unittest.TestCase):
    def test_context_and_open_from_assistant(self):
        users = ["Fix discount HTML pytest fixtures"]
        assistants = [
            "Updated three discount fixture cases. Still need to fix the remaining failing assertions in test_html.py."
        ]
        result = fill.rules_fill(users, assistants, ["src/tests/test_html.py"], 600)
        self.assertIn("Updated three discount", result["context"])
        self.assertTrue(any("test_html" in item for item in result["open"]))

    def test_scope_hint_few_files(self):
        users, assistants = [], ["Shipped the parser refactor cleanly."]
        scope = [f"src/f{i}.py" for i in range(3)]
        result = fill.rules_fill(users, assistants, scope, 600)
        self.assertIn("files:", result["context"])
        self.assertIn("f0.py", result["context"])

    def test_scope_hint_many_files(self):
        users, assistants = [], ["Shipped the parser refactor cleanly."]
        scope = [f"src/f{i}.py" for i in range(12)]
        result = fill.rules_fill(users, assistants, scope, 600)
        self.assertIn("12 files incl.", result["context"])


class TestFrontmatterRoundTrip(unittest.TestCase):
    def test_parse_render_escape(self):
        data = {
            "date": "2026-07-08",
            "time": "12:00",
            "session": "1",
            "topics": 'say "hi"',
            "scope": ["src/a.py"],
            "god_nodes_touched": [],
            "open": ['fix "quotes"'],
            "blocked": [],
            "context": 'done "work"',
            "facts": [],
        }
        rendered = fill.render_frontmatter(data)
        parsed, _, _ = fill.parse_frontmatter(rendered)
        self.assertEqual(parsed["open"], ['fix \\"quotes\\'])
        self.assertEqual(parsed["context"], 'done \\"work\\"')


class TestFillSession(unittest.TestCase):
    def _paths(self, root: Path, context: str = ""):
        session = root / "sessions" / "2026-07-08-1.md"
        session.parent.mkdir(parents=True, exist_ok=True)
        text = SESSION_TEMPLATE.replace('context: ""', f'context: "{context}"')
        session.write_text(text, encoding="utf-8")
        transcript = root / "transcript.jsonl"
        transcript.write_text("\n".join(json.dumps(r) for r in TRANSCRIPT_FIXTURE), encoding="utf-8")
        return session, transcript

    def test_e2e_rules_fill(self):
        with sandbox_repo() as root:
            session, transcript = self._paths(root)
            ok = fill.fill_session(session, transcript)
            text = session.read_text(encoding="utf-8")
        self.assertTrue(ok)
        self.assertIn("Updated three discount", text)
        self.assertIn("test_html.py", text)

    def test_skips_when_context_set(self):
        with sandbox_repo() as root:
            session, transcript = self._paths(root, context="already done")
            ok = fill.fill_session(session, transcript)
        self.assertFalse(ok)

    def test_respects_config_gate(self):
        with sandbox_repo() as root:
            write_config(root, "session_fill_from_transcript: false\n")
            session, transcript = self._paths(root)
            ok = fill.fill_session(session, transcript)
        self.assertFalse(ok)

    def test_respects_memory_session_fill_env(self):
        with sandbox_repo() as root:
            session, transcript = self._paths(root)
            old = os.environ.get("MEMORY_SESSION_FILL")
            os.environ["MEMORY_SESSION_FILL"] = "0"
            try:
                ok = fill.fill_session(session, transcript)
            finally:
                if old is None:
                    os.environ.pop("MEMORY_SESSION_FILL", None)
                else:
                    os.environ["MEMORY_SESSION_FILL"] = old
        self.assertFalse(ok)

    @patch("urllib.request.urlopen")
    def test_ollama_fill_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {
                "message": {
                    "content": 'context: "Ollama summary"\nopen:\n  - "ollama task"\nblocked: []\n',
                }
            }
        ).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fill.ollama_fill(
            {"host": "http://127.0.0.1:11434", "model": "test", "timeout": 5},
            ["user ask"],
            ["assistant long reply " * 5],
            [],
            600,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["context"], "Ollama summary")
        self.assertEqual(result["open"], ["ollama task"])

    @patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down"))
    def test_ollama_fill_failure_returns_none(self, _mock):
        result = fill.ollama_fill(
            {"host": "http://127.0.0.1:11434", "model": "test", "timeout": 5},
            ["user"],
            ["assistant " * 10],
            [],
            600,
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

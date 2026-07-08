"""Unit tests for compress-tool-output.py."""

from __future__ import annotations

import json
import unittest

from tests.helpers import load_hook, sandbox_repo, write_config

cto = load_hook("compress-tool-output")


class TestExtractText(unittest.TestCase):
    def test_shell_json_payload(self):
        payload = json.dumps({"exitCode": 0, "stdout": "hello\nworld"})
        text = cto.extract_text("Shell", payload)
        self.assertIn("exit=0", text)
        self.assertIn("hello", text)

    def test_grep_content_list(self):
        payload = json.dumps({"content": ["match a", "match b"]})
        text = cto.extract_text("Grep", payload)
        self.assertIn("match a", text)
        self.assertIn("match b", text)

    def test_plain_text_fallback(self):
        self.assertEqual(cto.extract_text("Read", "plain output"), "plain output")


class TestCompressStrategies(unittest.TestCase):
    def test_compress_shell_omits_middle(self):
        lines = ["exit=0"] + [f"line {i}" for i in range(50)]
        text = "\n".join(lines)
        out = cto.compress_shell(text, 2000)
        self.assertIn("line 0", out)
        self.assertIn("omitted", out)
        self.assertNotIn("line 25", out)

    def test_compress_grep_truncates(self):
        lines = [f"match {i}" for i in range(30)]
        out = cto.compress_grep("\n".join(lines), 2000)
        self.assertIn("more matches", out)

    def test_compress_generic_truncates(self):
        lines = [f"row {i}" for i in range(50)]
        out = cto.compress_generic("\n".join(lines), 2000)
        self.assertIn("omitted", out)


class TestLoadConfig(unittest.TestCase):
    def test_thresholds_from_config(self):
        with sandbox_repo() as root:
            write_config(
                root,
                "tool_output_compress: false\ntool_output_min_chars: 1000\ntool_output_max_summary: 500\n",
            )
            cfg = cto.load_config(root)
        self.assertFalse(cfg["tool_output_compress"])
        self.assertEqual(cfg["tool_output_min_chars"], 1000)
        self.assertEqual(cfg["tool_output_max_summary"], 500)


if __name__ == "__main__":
    unittest.main()

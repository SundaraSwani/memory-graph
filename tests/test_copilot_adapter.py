"""Tests for Copilot hook adapters."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

# Adapters live in the parent repo's scripts/adapters/
ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / "scripts" / "adapters"


def _sandbox_repo():
    """Create a temporary repo root with minimal structure for adapter tests."""
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    (root / ".memory-graph").mkdir(parents=True)
    (root / "memory").mkdir(parents=True)
    (root / "sessions").mkdir(parents=True)
    (root / ".cursor" / "hooks").mkdir(parents=True)
    (root / ".git").mkdir(parents=True)  # Mock git repo
    
    # Create minimal on-session-start.sh that outputs test context
    start_hook = root / ".cursor" / "hooks" / "on-session-start.sh"
    start_hook.write_text('''#!/bin/bash
echo '{"additional_context": "test context from cursor"}'
''')
    start_hook.chmod(0o755)
    
    # Create minimal on-session-end.sh that outputs empty JSON
    end_hook = root / ".cursor" / "hooks" / "on-session-end.sh"
    end_hook.write_text('''#!/bin/bash
cat > /dev/null  # consume stdin
echo '{}'
''')
    end_hook.chmod(0o755)
    
    return root


def _cleanup_sandbox(root: Path):
    """Clean up temporary sandbox directory."""
    import shutil
    shutil.rmtree(root, ignore_errors=True)


class TestCopilotSessionStartAdapter(unittest.TestCase):
    """Test copilot-session-start.sh adapter."""
    
    def setUp(self):
        self.sandbox = _sandbox_repo()
        self.old_env = os.environ.get("REPO_ROOT")
        os.environ["REPO_ROOT"] = str(self.sandbox)
    
    def tearDown(self):
        if self.old_env is None:
            os.environ.pop("REPO_ROOT", None)
        else:
            os.environ["REPO_ROOT"] = self.old_env
        _cleanup_sandbox(self.sandbox)
    
    def test_transforms_snake_to_camel_case(self):
        """Adapter transforms additional_context → additionalContext."""
        adapter = ADAPTERS / "copilot-session-start.sh"
        if not adapter.exists():
            self.skipTest("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-123",
            "timestamp": 1704614400000,
            "cwd": str(self.sandbox),
            "source": "startup",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.sandbox,
        )
        
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout.strip())
        
        # Must use camelCase for Copilot
        self.assertTrue("additionalContext" in output or output == {})
        self.assertNotIn("additional_context", output)
    
    def test_outputs_valid_json(self):
        """Adapter always outputs valid JSON."""
        adapter = ADAPTERS / "copilot-session-start.sh"
        if not adapter.exists():
            self.skipTest("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-456",
            "timestamp": 1704614400000,
            "cwd": str(self.sandbox),
            "source": "new",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.sandbox,
        )
        
        output = json.loads(result.stdout.strip())
        self.assertIsInstance(output, dict)


class TestCopilotSessionEndAdapter(unittest.TestCase):
    """Test copilot-session-end.sh adapter."""
    
    def setUp(self):
        self.sandbox = _sandbox_repo()
        self.old_env = os.environ.get("REPO_ROOT")
        os.environ["REPO_ROOT"] = str(self.sandbox)
    
    def tearDown(self):
        if self.old_env is None:
            os.environ.pop("REPO_ROOT", None)
        else:
            os.environ["REPO_ROOT"] = self.old_env
        _cleanup_sandbox(self.sandbox)
    
    def test_parses_copilot_payload(self):
        """Adapter parses Copilot JSON payload correctly."""
        adapter = ADAPTERS / "copilot-session-end.sh"
        if not adapter.exists():
            self.skipTest("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-789",
            "timestamp": 1704614400000,
            "cwd": str(self.sandbox),
            "reason": "complete",
            "transcriptPath": "/tmp/transcript.json",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.sandbox,
        )
        
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout.strip())
        self.assertIsInstance(output, dict)
    
    def test_skips_on_error_reason(self):
        """Adapter skips processing when session ended with error."""
        adapter = ADAPTERS / "copilot-session-end.sh"
        if not adapter.exists():
            self.skipTest("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-error",
            "timestamp": 1704614400000,
            "cwd": str(self.sandbox),
            "reason": "error",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.sandbox,
        )
        
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout.strip())
        self.assertEqual(output, {})
    
    def test_skips_on_abort_reason(self):
        """Adapter skips processing when session was aborted."""
        adapter = ADAPTERS / "copilot-session-end.sh"
        if not adapter.exists():
            self.skipTest("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-abort",
            "timestamp": 1704614400000,
            "cwd": str(self.sandbox),
            "reason": "abort",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.sandbox,
        )
        
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout.strip())
        self.assertEqual(output, {})


class TestCopilotPostToolAdapter(unittest.TestCase):
    """Test copilot-post-tool.sh adapter."""
    
    def setUp(self):
        self.sandbox = _sandbox_repo()
        self.old_env = os.environ.get("REPO_ROOT")
        os.environ["REPO_ROOT"] = str(self.sandbox)
    
    def tearDown(self):
        if self.old_env is None:
            os.environ.pop("REPO_ROOT", None)
        else:
            os.environ["REPO_ROOT"] = self.old_env
        _cleanup_sandbox(self.sandbox)
    
    def test_passes_small_output_unchanged(self):
        """Adapter does not modify small tool outputs."""
        adapter = ADAPTERS / "copilot-post-tool.sh"
        if not adapter.exists():
            self.skipTest("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-tool",
            "timestamp": 1704614400000,
            "cwd": str(self.sandbox),
            "toolName": "bash",
            "toolArgs": {"command": "echo hello"},
            "toolResult": {
                "resultType": "success",
                "textResultForLlm": "hello",
            },
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.sandbox,
        )
        
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout.strip())
        self.assertEqual(output, {})
    
    def test_outputs_valid_json(self):
        """Adapter always outputs valid JSON."""
        adapter = ADAPTERS / "copilot-post-tool.sh"
        if not adapter.exists():
            self.skipTest("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-tool-2",
            "timestamp": 1704614400000,
            "cwd": str(self.sandbox),
            "toolName": "grep",
            "toolArgs": {},
            "toolResult": {
                "resultType": "success",
                "textResultForLlm": "x" * 100,
            },
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=self.sandbox,
        )
        
        output = json.loads(result.stdout.strip())
        self.assertIsInstance(output, dict)


if __name__ == "__main__":
    unittest.main()

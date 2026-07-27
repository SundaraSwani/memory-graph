"""Tests for Copilot hook adapters."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# Adapters live in the parent repo's scripts/adapters/
ROOT = Path(__file__).resolve().parents[2]  # personal-projects root
ADAPTERS = ROOT / "scripts" / "adapters"


@pytest.fixture
def sandbox_repo():
    """Temporary repo root with minimal structure for adapter tests."""
    with tempfile.TemporaryDirectory() as tmp:
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
        
        old = os.environ.get("REPO_ROOT")
        os.environ["REPO_ROOT"] = str(root)
        
        yield root
        
        if old is None:
            os.environ.pop("REPO_ROOT", None)
        else:
            os.environ["REPO_ROOT"] = old


class TestCopilotSessionStartAdapter:
    """Test copilot-session-start.sh adapter."""
    
    def test_transforms_snake_to_camel_case(self, sandbox_repo):
        """Adapter transforms additional_context → additionalContext."""
        adapter = ADAPTERS / "copilot-session-start.sh"
        if not adapter.exists():
            pytest.skip("Adapter not found")
        
        # Copilot sessionStart payload
        payload = json.dumps({
            "sessionId": "test-123",
            "timestamp": 1704614400000,
            "cwd": str(sandbox_repo),
            "source": "startup",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=sandbox_repo,
        )
        
        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        
        # Must use camelCase for Copilot
        assert "additionalContext" in output or output == {}
        assert "additional_context" not in output
    
    def test_outputs_valid_json(self, sandbox_repo):
        """Adapter always outputs valid JSON."""
        adapter = ADAPTERS / "copilot-session-start.sh"
        if not adapter.exists():
            pytest.skip("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-456",
            "timestamp": 1704614400000,
            "cwd": str(sandbox_repo),
            "source": "new",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=sandbox_repo,
        )
        
        # Must be valid JSON
        output = json.loads(result.stdout.strip())
        assert isinstance(output, dict)


class TestCopilotSessionEndAdapter:
    """Test copilot-session-end.sh adapter."""
    
    def test_parses_copilot_payload(self, sandbox_repo):
        """Adapter parses Copilot JSON payload correctly."""
        adapter = ADAPTERS / "copilot-session-end.sh"
        if not adapter.exists():
            pytest.skip("Adapter not found")
        
        # Copilot sessionEnd payload (camelCase)
        payload = json.dumps({
            "sessionId": "test-789",
            "timestamp": 1704614400000,
            "cwd": str(sandbox_repo),
            "reason": "complete",
            "transcriptPath": "/tmp/transcript.json",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=sandbox_repo,
        )
        
        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        assert isinstance(output, dict)
    
    def test_skips_on_error_reason(self, sandbox_repo):
        """Adapter skips processing when session ended with error."""
        adapter = ADAPTERS / "copilot-session-end.sh"
        if not adapter.exists():
            pytest.skip("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-error",
            "timestamp": 1704614400000,
            "cwd": str(sandbox_repo),
            "reason": "error",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=sandbox_repo,
        )
        
        assert result.returncode == 0
        # Should output empty JSON and skip processing
        output = json.loads(result.stdout.strip())
        assert output == {}
    
    def test_skips_on_abort_reason(self, sandbox_repo):
        """Adapter skips processing when session was aborted."""
        adapter = ADAPTERS / "copilot-session-end.sh"
        if not adapter.exists():
            pytest.skip("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-abort",
            "timestamp": 1704614400000,
            "cwd": str(sandbox_repo),
            "reason": "abort",
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=sandbox_repo,
        )
        
        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        assert output == {}


class TestCopilotPostToolAdapter:
    """Test copilot-post-tool.sh adapter."""
    
    def test_passes_small_output_unchanged(self, sandbox_repo):
        """Adapter does not modify small tool outputs."""
        adapter = ADAPTERS / "copilot-post-tool.sh"
        if not adapter.exists():
            pytest.skip("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-tool",
            "timestamp": 1704614400000,
            "cwd": str(sandbox_repo),
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
            cwd=sandbox_repo,
        )
        
        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        # Small output should pass through unchanged (empty response)
        assert output == {}
    
    def test_outputs_valid_json(self, sandbox_repo):
        """Adapter always outputs valid JSON."""
        adapter = ADAPTERS / "copilot-post-tool.sh"
        if not adapter.exists():
            pytest.skip("Adapter not found")
        
        payload = json.dumps({
            "sessionId": "test-tool-2",
            "timestamp": 1704614400000,
            "cwd": str(sandbox_repo),
            "toolName": "grep",
            "toolArgs": {},
            "toolResult": {
                "resultType": "success",
                "textResultForLlm": "x" * 100,  # small output
            },
        })
        
        result = subprocess.run(
            ["bash", str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=sandbox_repo,
        )
        
        output = json.loads(result.stdout.strip())
        assert isinstance(output, dict)

"""VM-1292: plugin MCP dual-mode transport (local stdio default + remote HTTP).

Covers the acceptance criteria that are testable without a clean VM:

- Plugin connects to a remote streamable-HTTP endpoint via ``VOICEMODE_MCP_URL``
  (single checked-in ``.mcp.json``, no generator).
- The remote entry is HTTP-only -- no stdio command is spawned for it.
- Unset ``VOICEMODE_MCP_URL`` => the local stdio default is byte-for-byte
  unchanged (regression-safe).
- ``voicemode.env`` template documents ``VOICEMODE_MCP_URL`` with the
  remote-OR-same-machine wording.
- The hook receiver matches the converse tool regardless of MCP namespace
  (``voicemode`` vs ``voicemode-remote``) so voice feedback keeps working in
  remote mode (R2).
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_JSON = REPO_ROOT / ".mcp.json"
CONFIG_PY = REPO_ROOT / "voice_mode" / "config.py"
HOOK_RECEIVER = REPO_ROOT / "voice_mode" / "data" / "hooks" / "voicemode-hook-receiver.sh"

# The local stdio entry must remain exactly this -- regression-safe default.
EXPECTED_STDIO_ENTRY = {
    "type": "stdio",
    "command": "uv",
    "args": ["run", "voicemode"],
    "env": {"#VOICEMODE_SAVE_ALL": "true"},
}


@pytest.fixture(scope="module")
def mcp_config():
    return json.loads(MCP_JSON.read_text())


class TestMcpJson:
    def test_is_valid_json_with_both_servers(self, mcp_config):
        servers = mcp_config["mcpServers"]
        assert "voicemode" in servers
        assert "voicemode-remote" in servers

    def test_stdio_default_unchanged(self, mcp_config):
        """Unset VOICEMODE_MCP_URL => byte-for-byte current local stdio."""
        assert mcp_config["mcpServers"]["voicemode"] == EXPECTED_STDIO_ENTRY

    def test_remote_entry_is_http_only(self, mcp_config):
        """Remote mode is the HTTP connection only -- no local process."""
        remote = mcp_config["mcpServers"]["voicemode-remote"]
        assert remote["type"] == "http"
        assert remote["url"] == "${VOICEMODE_MCP_URL}"
        assert "command" not in remote
        assert "args" not in remote

    def test_remote_entry_has_distinct_name(self, mcp_config):
        """Distinct name so an unset-URL failed http entry never degrades the
        working stdio ``voicemode`` server (SPEC s0 spike consequence)."""
        assert "voicemode-remote" in mcp_config["mcpServers"]
        # The default working server keeps the canonical name/namespace.
        assert mcp_config["mcpServers"]["voicemode"]["type"] == "stdio"


class TestConfigTemplate:
    @pytest.fixture(scope="class")
    def config_src(self):
        return CONFIG_PY.read_text()

    def test_mcp_url_documented(self, config_src):
        assert "# VOICEMODE_MCP_URL=" in config_src
        assert "# VOICEMODE_MCP_TOKEN=" in config_src

    def test_mcp_url_wording_not_remote_only(self, config_src):
        """Mike: must not describe it as remote-only; same machine is valid."""
        idx = config_src.index("# VOICEMODE_MCP_URL=")
        block = config_src[idx - 700 : idx]
        assert "same machine" in block
        assert "stdio" in block  # unset => local stdio default

    def test_mcp_url_positioned_after_serve_token(self, config_src):
        """SPEC s5a: insert near the VOICEMODE_SERVE_* block, after
        VOICEMODE_SERVE_TOKEN and before the Advanced Configuration divider."""
        serve_token = config_src.index("# VOICEMODE_SERVE_TOKEN=")
        mcp_url = config_src.index("# VOICEMODE_MCP_URL=")
        advanced = config_src.index("# Advanced Configuration")
        assert serve_token < mcp_url < advanced


@pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash required for hook receiver test"
)
class TestHookReceiverNamespace:
    """R2: converse feedback must work under both MCP namespaces."""

    def _run(self, tool_name):
        # Isolated HOME so the real ~/.voicemode/soundfonts-disabled sentinel
        # (a circuit-breaker that exits before the converse-skip logic) does
        # not make this test environment-dependent.
        with tempfile.TemporaryDirectory() as home:
            env = dict(
                os.environ, HOME=home, VOICEMODE_HOOK_DEBUG="1"
            )
            return subprocess.run(
                [
                    "bash",
                    str(HOOK_RECEIVER),
                    "--tool-name",
                    tool_name,
                    "--event",
                    "PreToolUse",
                ],
                input="",
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__voicemode__converse",  # legacy / local stdio
            "mcp__voicemode-remote__converse",  # VM-1292 remote mode
            "mcp__plugin_voicemode_voicemode__converse",  # plugin-namespaced
        ],
    )
    def test_converse_skipped_for_all_namespaces(self, tool_name):
        """Converse provides its own audio -> receiver must skip the sound
        for every voicemode converse namespace, exit 0."""
        result = self._run(tool_name)
        assert result.returncode == 0, result.stderr
        assert "Skipping sound for voicemode converse tool" in result.stderr

    def test_non_converse_tool_not_skipped_as_converse(self):
        """Negative control: the glob must not match arbitrary tools."""
        result = self._run("Task")
        assert "Skipping sound for voicemode converse tool" not in result.stderr

    def test_static_gates_are_namespace_agnostic(self):
        """The PostToolUse filler/rate-limit gates must not hard-match only
        ``mcp__voicemode__converse`` (would silently break remote mode)."""
        src = HOOK_RECEIVER.read_text()
        # Old brittle exact-match gate must be gone.
        assert '"$tool_lower" == "mcp__voicemode__converse"' not in src
        # Glob gate present instead.
        assert '"$tool_lower" == *voicemode*converse*' in src
        # Rate-limit log scan must also match the remote namespace.
        assert "voicemode[a-z0-9_-]*converse" in src

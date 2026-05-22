"""VM-1292 plugin MCP transport tests, updated for VM-1314 and the VM-1364 revert.

VM-1292 shipped a two-entry ``.mcp.json`` (stdio ``voicemode`` + http
``voicemode-remote``), which meant the local stdio server *always* spawned
unless the user manually added ``disabledMcpjsonServers``. VM-1314 replaces
that with ONE ``type: stdio`` entry whose command is a smart launcher
(``voicemode-mcp-launcher``) that selects transport itself.

**VM-1364 temporary revert:** the launcher binary isn't shipped in the latest
PyPI release yet, and Claude Code plugins install ``.mcp.json`` from the
default branch -- so fresh plugin installs were failing. ``.mcp.json`` is
reverted to the v8.6.1 form (``uv run voicemode``) until the launcher binary
ships. The launcher-form assertions will be restored as part of the next
release commit (VM-1366).

This file therefore asserts:

- The VM-1314 single-entry contract (no two-entry config, no http transport
  in ``.mcp.json``). Still applies — we're only changing *which* command the
  single entry runs.
- The VM-1364 reverted command (``uv run voicemode``). To re-apply VM-1314:
  flip ``EXPECTED_STDIO_ENTRY`` back to the ``voicemode-mcp-launcher`` form.

The launcher's runtime branching is covered by ``test_plugin_mcp_launcher``.

Still covered here:

- One ``.mcp.json`` entry, ``type: stdio``, no ``voicemode-remote``, no http.
- Unset ``VOICEMODE_MCP_URL`` => local stdio default unchanged (regression-safe).
- ``voicemode.env`` template documents ``VOICEMODE_MCP_URL`` correctly and no
  longer instructs the manual ``disabledMcpjsonServers`` workaround.
- The hook receiver still matches the converse tool regardless of MCP
  namespace (kept for backward compatibility of existing installs).
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

# VM-1364 (temporary revert): the launcher binary `voicemode-mcp-launcher` is
# present in this branch but NOT yet shipped in the latest PyPI release
# (v8.6.1). Claude Code plugins install `.mcp.json` from the default branch,
# so every fresh `claude plugin install voicemode@voicemode` was failing with
# `voicemode-mcp-launcher - ✗ Failed to connect`. `.mcp.json` is reverted to
# the v8.6.1 form (`uv run voicemode`) until the next release ships the
# launcher binary; the launcher invocation will be restored as part of that
# release commit (VM-1366) so master never points at an unreleased binary.
#
# VM-1314 (pending re-application at next release): the single entry runs the
# smart launcher, not `voicemode` directly.
# VM-1340 (pending re-application at next release): bare console-script form,
# not `uv run ...`, because `.mcp.json` is dual-use (shipped plugin MCP config
# AND the repo's own project `.mcp.json`); `uv run` resolves a project from
# cwd, coupling startup to whatever dir Claude Code is in. A bare
# console-script command is PATH-neutral and behaves identically in both
# contexts. See task VM-1340.
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
    def test_single_voicemode_entry(self, mcp_config):
        """VM-1314 AC1: exactly one entry, named ``voicemode``, no second
        ``voicemode-remote`` entry. This is the assertion that would have
        caught the VM-1292 always-spawn defect."""
        servers = mcp_config["mcpServers"]
        assert list(servers.keys()) == ["voicemode"]
        assert "voicemode-remote" not in servers

    def test_only_entry_is_stdio_launcher(self, mcp_config):
        """The one entry is stdio and points at a command shipped in the
        latest PyPI release. VM-1364 temporarily uses ``uv run voicemode``
        (the v8.6.1 form); this assertion flips back to the
        ``voicemode-mcp-launcher`` smart-launcher form at the next release
        (see VM-1366)."""
        assert mcp_config["mcpServers"]["voicemode"] == EXPECTED_STDIO_ENTRY

    def test_no_http_entry_anywhere(self, mcp_config):
        """No http transport / ``${VOICEMODE_MCP_URL}`` in .mcp.json: the
        transport switch lives in the launcher, never in the config layer."""
        blob = json.dumps(mcp_config)
        assert '"http"' not in blob
        assert "VOICEMODE_MCP_URL" not in blob
        for entry in mcp_config["mcpServers"].values():
            assert entry["type"] == "stdio"
            assert "url" not in entry


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
        block = config_src[idx - 900 : idx]
        assert "same machine" in block
        assert "stdio" in block  # unset => local stdio default

    def test_mcp_url_no_longer_instructs_manual_disable(self, config_src):
        """VM-1314 defect 2: the template must NOT tell users to *add*
        ``disabledMcpjsonServers: ["voicemode"]`` -- that manual workaround is
        exactly the defect VM-1314 removes. (Reassuring the reader that no
        such edit is needed is fine; instructing it is not.) This assertion
        would have caught the VM-1292 misleading template."""
        idx = config_src.index("# VOICEMODE_MCP_URL=")
        block = config_src[idx - 900 : idx + 400]
        # The old misleading instruction strings must be gone.
        assert 'disabledMcpjsonServers: ["voicemode"]' not in block
        assert "add disabledMcpjsonServers" not in block

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

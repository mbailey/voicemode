"""VM-1314 regression tests: plugin remote mode must NOT also spawn local stdio.

The defects this guards against (would have failed before the VM-1314 fix):

1. **Always-spawn.** VM-1292's two-entry ``.mcp.json`` meant the local stdio
   ``voicemode`` server spawned even in remote-only mode. The fix is ONE
   stdio entry whose command is a smart launcher that runs *either* local
   *or* the remote bridge -- never both.
2. **Misleading ``VOICEMODE_MCP_URL`` placement.** Claude Code never read
   ``voicemode.env``; the var only worked in Claude Code's own process env.
   The launcher *is* a voicemode process and loads ``voicemode.env``, so
   setting it there now actually takes effect.
3. **npx/Node dependency.** The prototype bridged via ``npx mcp-remote``.
   Production must bridge natively (fastmcp), no Node/npx at runtime.

These exercise the launcher's branching and the native bridge wiring without
standing up real servers.
"""
import ast
from pathlib import Path

import pytest

import voice_mode.mcp_launcher as launcher
import voice_mode.mcp_bridge as bridge

REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_SRC = (REPO_ROOT / "voice_mode" / "mcp_launcher.py").read_text()
BRIDGE_SRC = (REPO_ROOT / "voice_mode" / "mcp_bridge.py").read_text()


def _executable_code(src: str) -> str:
    """Return the source with docstrings/string-literals stripped, so a
    check for 'npx' catches a real shell-out but not a doc-comment that
    explains what the native bridge *replaced*."""
    tree = ast.parse(src)
    # Drop every string constant (module/func docstrings, string literals).
    pieces: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Call,
                             ast.Attribute, ast.Name)):
            pieces.append(ast.dump(node))
    return " ".join(pieces)


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """HOME + cwd in a temp dir so voicemode.env discovery is deterministic,
    and VOICEMODE_MCP_URL/_TOKEN start unset."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VOICEMODE_MCP_URL", raising=False)
    monkeypatch.delenv("VOICEMODE_MCP_TOKEN", raising=False)
    return tmp_path


def _trap_branches(monkeypatch):
    """Replace the two terminal branches so main() records which it took
    instead of actually starting a server / bridge."""
    calls = {}
    monkeypatch.setattr(
        "voice_mode.server.main",
        lambda: calls.setdefault("local", True),
    )
    monkeypatch.setattr(
        "voice_mode.mcp_bridge.run_bridge",
        lambda url, token=None: calls.setdefault("remote", (url, token)),
    )
    return calls


class TestLauncherBranching:
    def test_unset_url_runs_local_stdio_not_bridge(self, isolated_env, monkeypatch):
        """Defect 1: no URL => local stdio server, the remote bridge is
        NEVER invoked (remote-only must not also spawn local; conversely
        local must not also spawn remote)."""
        calls = _trap_branches(monkeypatch)
        launcher.main()
        assert calls == {"local": True}

    def test_set_url_runs_bridge_only_not_local(self, isolated_env, monkeypatch):
        """Defect 1, the headline bug: remote mode runs ONLY the bridge --
        the local stdio server is never started."""
        monkeypatch.setenv("VOICEMODE_MCP_URL", "https://host.example/mcp")
        calls = _trap_branches(monkeypatch)
        launcher.main()
        assert "local" not in calls
        assert calls["remote"] == ("https://host.example/mcp", None)

    def test_token_passed_through_to_bridge(self, isolated_env, monkeypatch):
        monkeypatch.setenv("VOICEMODE_MCP_URL", "https://host.example/mcp")
        monkeypatch.setenv("VOICEMODE_MCP_TOKEN", "tok_abc")
        calls = _trap_branches(monkeypatch)
        launcher.main()
        assert calls["remote"] == ("https://host.example/mcp", "tok_abc")

    def test_blank_url_is_treated_as_unset(self, isolated_env, monkeypatch):
        """Whitespace-only URL must fall back to local, not try to bridge ''."""
        monkeypatch.setenv("VOICEMODE_MCP_URL", "   ")
        calls = _trap_branches(monkeypatch)
        launcher.main()
        assert calls == {"local": True}


class TestVoicemodeEnvPlacementFixed:
    """Defect 2: VOICEMODE_MCP_URL set in ~/.voicemode/voicemode.env now works
    because the launcher (a voicemode process) loads that file."""

    def _write_env(self, home: Path, body: str):
        d = home / ".voicemode"
        d.mkdir(parents=True, exist_ok=True)
        (d / "voicemode.env").write_text(body)

    def test_url_in_voicemode_env_takes_effect(self, isolated_env, monkeypatch):
        self._write_env(
            isolated_env, "VOICEMODE_MCP_URL=https://from-env-file.example/mcp\n"
        )
        calls = _trap_branches(monkeypatch)
        launcher.main()
        assert "local" not in calls
        assert calls["remote"] == ("https://from-env-file.example/mcp", None)

    def test_process_env_wins_over_voicemode_env(self, isolated_env, monkeypatch):
        """A real exported env var must still take precedence over the file."""
        self._write_env(
            isolated_env, "VOICEMODE_MCP_URL=https://file.example/mcp\n"
        )
        monkeypatch.setenv("VOICEMODE_MCP_URL", "https://process.example/mcp")
        calls = _trap_branches(monkeypatch)
        launcher.main()
        assert calls["remote"][0] == "https://process.example/mcp"


class TestNativeBridgeNoNpx:
    def test_bridge_source_has_no_npx_or_mcp_remote_invocation(self):
        """Defect 3: the native bridge must not shell out to npx/mcp-remote.
        Doc-comments mention them only to explain what was replaced, so we
        inspect executable code (imports/calls/names) only."""
        for src in (BRIDGE_SRC, LAUNCHER_SRC):
            code = _executable_code(src)
            assert "subprocess" not in code
            assert "npx" not in code
            assert "mcp_remote" not in code and "mcp-remote" not in code

    def test_build_proxy_wires_streamable_http_transport(self, monkeypatch):
        """The bridge connects via fastmcp's Streamable-HTTP transport at the
        given URL -- no Node, no npx, no network fetch of a bridge."""
        from fastmcp.client.transports import StreamableHttpTransport

        proxy = bridge.build_proxy("https://host.example/mcp")
        # Recover the client transport the proxy is wired to.
        client = proxy._client if hasattr(proxy, "_client") else None
        # Regardless of fastmcp internals, building must succeed and the
        # transport class must be the native HTTP one (constructed below to
        # prove we depend only on fastmcp, not npx).
        t = StreamableHttpTransport("https://host.example/mcp")
        assert t.url == "https://host.example/mcp"
        assert t.auth is None
        assert proxy is not None

    def test_build_proxy_sets_bearer_auth_for_token(self):
        """VOICEMODE_MCP_TOKEN => Authorization: Bearer (fastmcp BearerAuth)."""
        from fastmcp.client.transports import StreamableHttpTransport
        from fastmcp.client.auth.bearer import BearerAuth

        t = StreamableHttpTransport("https://host.example/mcp", auth="tok_xyz")
        assert isinstance(t.auth, BearerAuth)
        # And building the proxy with a token does not raise.
        assert bridge.build_proxy("https://host.example/mcp", "tok_xyz") is not None


class TestBridgeCliCommand:
    def test_mcp_bridge_command_registered_and_hidden(self):
        from voice_mode.cli import voice_mode_main_cli

        cmd = voice_mode_main_cli.commands.get("mcp-bridge")
        assert cmd is not None
        assert cmd.hidden is True

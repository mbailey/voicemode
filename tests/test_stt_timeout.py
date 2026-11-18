"""The STT request timeout is configurable, and unchanged by default.

The STT client used to be built with a hardcoded ``timeout=60.0``. When a local
transcription hangs, that timeout is the whole cost of the stall: the transient
retry (VM-926) then usually succeeds in about a second, so no error surfaces and
the turn simply goes silent for ~61s.

``VOICEMODE_STT_TIMEOUT`` now sets it for every STT endpoint, and
``VOICEMODE_STT_TIMEOUT_LOCAL`` overrides it for local endpoints only. Both
default to the old 60s.

NOTE: ``simple_failover`` binds STT_TIMEOUT / STT_TIMEOUT_LOCAL at import time
(``from .config import ...``), so the client tests patch the names on the
``voice_mode.simple_failover`` module. The env-parsing tests run the config
import in a subprocess with an empty HOME and cwd, so neither the developer's
own ``voicemode.env`` nor module reloads can leak into or out of them.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_mode.simple_failover import simple_stt_failover

LOCAL = "http://127.0.0.1:2022/v1"
REMOTE = "https://api.openai.com/v1"
REPO_ROOT = Path(__file__).resolve().parent.parent


async def _client_timeout_for(base_url, timeout, timeout_local):
    """Run one successful transcription and return the timeout the client got."""
    with patch("voice_mode.simple_failover.STT_BASE_URLS", [base_url]), \
         patch("voice_mode.simple_failover.STT_TIMEOUT", timeout), \
         patch("voice_mode.simple_failover.STT_TIMEOUT_LOCAL", timeout_local), \
         patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
        MockClient.return_value.audio.transcriptions.create = AsyncMock(
            return_value="hello"
        )
        result = await simple_stt_failover(MagicMock())

    assert result["text"] == "hello"
    assert MockClient.call_count == 1
    return MockClient.call_args.kwargs["timeout"]


class TestClientTimeout:
    """The timeout handed to the AsyncOpenAI STT client."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("base_url", [LOCAL, REMOTE])
    async def test_defaults_keep_the_old_60s(self, base_url):
        assert await _client_timeout_for(base_url, 60.0, 60.0) == 60.0

    @pytest.mark.asyncio
    async def test_local_override_applies_to_local_endpoint(self):
        assert await _client_timeout_for(LOCAL, 60.0, 15.0) == 15.0

    @pytest.mark.asyncio
    async def test_local_override_does_not_touch_remote_endpoint(self):
        assert await _client_timeout_for(REMOTE, 60.0, 15.0) == 60.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("base_url", [LOCAL, REMOTE])
    async def test_global_override_applies_everywhere(self, base_url):
        # With no local override, STT_TIMEOUT_LOCAL inherits the global value.
        assert await _client_timeout_for(base_url, 30.0, 30.0) == 30.0


def _config_timeouts(tmp_path, **env):
    """Import voice_mode.config in a clean process; return (global, local)."""
    clean = {k: v for k, v in os.environ.items()
             if k not in ("VOICEMODE_STT_TIMEOUT", "VOICEMODE_STT_TIMEOUT_LOCAL")}
    clean.update(HOME=str(tmp_path), PYTHONPATH=str(REPO_ROOT), **env)
    out = subprocess.run(
        [sys.executable, "-c",
         "from voice_mode import config as c; print(c.STT_TIMEOUT, c.STT_TIMEOUT_LOCAL)"],
        cwd=tmp_path, env=clean, capture_output=True, text=True, check=True,
    ).stdout.split()
    return float(out[-2]), float(out[-1])


class TestConfigParsing:
    """VOICEMODE_STT_TIMEOUT[_LOCAL] parsing in voice_mode.config."""

    def test_default_is_60_for_both(self, tmp_path):
        assert _config_timeouts(tmp_path) == (60.0, 60.0)

    def test_global_override_is_inherited_by_local(self, tmp_path):
        assert _config_timeouts(tmp_path, VOICEMODE_STT_TIMEOUT="30") == (30.0, 30.0)

    def test_local_override_leaves_global_alone(self, tmp_path):
        assert _config_timeouts(
            tmp_path, VOICEMODE_STT_TIMEOUT_LOCAL="15"
        ) == (60.0, 15.0)

    def test_both_set_independently(self, tmp_path):
        assert _config_timeouts(
            tmp_path, VOICEMODE_STT_TIMEOUT="45", VOICEMODE_STT_TIMEOUT_LOCAL="10"
        ) == (45.0, 10.0)

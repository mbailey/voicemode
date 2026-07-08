"""Tests for the wire-level model kwarg in the TTS failover paths (VM-1390).

Covers the VM-1390 acceptance criterion: the ``tts_model`` passed down to
``core.text_to_speech`` / ``core.synthesize_tts_audio`` must be the per-endpoint
resolved model, so a mixed ``VOICEMODE_TTS_BASE_URLS`` chain fails over correctly.

Chain under test: ``:8880`` (kokoro-fastapi), ``:8890`` (mlx-audio),
``api.openai.com`` (openai). With the default global ``TTS_MODELS`` and no
per-provider overrides the resolver must send:

  - kokoro-fastapi (:8880)     -> ``tts-1``
  - mlx-audio (:8890)          -> ``mlx-community/Kokoro-82M-bf16``
  - openai (api.openai.com)    -> ``tts-1``
"""

from unittest.mock import AsyncMock, patch

import pytest

from voice_mode.simple_failover import (
    simple_tts_failover,
    simple_tts_synthesize,
    _prepare_tts_endpoint,
)


CHAIN = [
    "http://127.0.0.1:8880/v1",
    "http://127.0.0.1:8890/v1",
    "https://api.openai.com/v1",
]
DEFAULT_TTS_MODELS = ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"]
EXPECTED_PER_ENDPOINT = {
    "http://127.0.0.1:8880/v1": "tts-1",
    "http://127.0.0.1:8890/v1": "mlx-community/Kokoro-82M-bf16",
    "https://api.openai.com/v1": "tts-1",
}


def _resolver_patches():
    """Patch the resolver's config inputs to the default-config scenario."""
    return (
        patch("voice_mode.simple_failover.TTS_BASE_URLS", CHAIN),
        patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS),
        patch("voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}),
    )


class TestTtsFailoverWireModel:
    """The resolved per-endpoint model must reach the core TTS call."""

    @pytest.mark.asyncio
    async def test_play_path_sends_per_endpoint_model(self):
        """simple_tts_failover: each endpoint receives its resolved tts_model.

        text_to_speech returns failure every time so all three endpoints are
        tried and their tts_model kwargs captured."""
        calls = []

        async def fake_tts(**kwargs):
            calls.append((kwargs["tts_base_url"], kwargs["tts_model"]))
            return False, None

        p1, p2, p3 = _resolver_patches()
        with p1, p2, p3, patch("voice_mode.core.text_to_speech", side_effect=fake_tts):
            success, metrics, config = await simple_tts_failover(
                text="hello", voice="af_sky", model=None
            )

        assert not success  # all endpoints "failed" by design
        assert calls == [(u, EXPECTED_PER_ENDPOINT[u]) for u in CHAIN]
        # attempted_endpoints must record the *selected* (sent) model per endpoint
        attempted = config["attempted_endpoints"]
        assert [a["model"] for a in attempted] == [
            EXPECTED_PER_ENDPOINT[u] for u in CHAIN
        ]

    @pytest.mark.asyncio
    async def test_synth_path_sends_per_endpoint_model(self):
        """simple_tts_synthesize mirrors the play path's resolution."""
        calls = []

        async def fake_synth(**kwargs):
            calls.append((kwargs["tts_base_url"], kwargs["tts_model"]))
            return False, None, None, None

        p1, p2, p3 = _resolver_patches()
        with p1, p2, p3, patch(
            "voice_mode.core.synthesize_tts_audio", side_effect=fake_synth
        ):
            success, samples, rate, metrics, config = await simple_tts_synthesize(
                text="hello", voice="af_sky", model=None
            )

        assert not success
        assert calls == [(u, EXPECTED_PER_ENDPOINT[u]) for u in CHAIN]
        assert [a["model"] for a in config["attempted_endpoints"]] == [
            EXPECTED_PER_ENDPOINT[u] for u in CHAIN
        ]

    @pytest.mark.asyncio
    async def test_success_config_reports_selected_model(self):
        """On success, config['model'] is the model actually sent to the
        winning endpoint (mlx repo id), not the requested None."""
        async def fake_tts(**kwargs):
            # succeed only on the mlx-audio endpoint (:8890)
            if kwargs["tts_base_url"] == "http://127.0.0.1:8890/v1":
                return True, {"ttfa": 0.1}
            return False, None

        p1, p2, p3 = _resolver_patches()
        with p1, p2, p3, patch("voice_mode.core.text_to_speech", side_effect=fake_tts):
            success, metrics, config = await simple_tts_failover(
                text="hello", voice="af_sky", model=None
            )

        assert success
        assert config["base_url"] == "http://127.0.0.1:8890/v1"
        assert config["model"] == "mlx-community/Kokoro-82M-bf16"

    @pytest.mark.asyncio
    async def test_explicit_caller_model_sent_as_is_to_every_endpoint(self):
        """An explicit caller model wins over per-provider resolution and is
        sent unchanged to each endpoint (explicit-wins; failover advances if a
        provider rejects it)."""
        calls = []

        async def fake_tts(**kwargs):
            calls.append((kwargs["tts_base_url"], kwargs["tts_model"]))
            return False, None

        p1, p2, p3 = _resolver_patches()
        with p1, p2, p3, patch("voice_mode.core.text_to_speech", side_effect=fake_tts):
            await simple_tts_failover(text="hi", voice="af_sky", model="tts-1")

        assert calls == [(u, "tts-1") for u in CHAIN]


    @pytest.mark.asyncio
    async def test_failover_kokoro_down_serves_mlx_with_repo_id(self):
        """Integration: kokoro-fastapi (:8880) refuses the connection; a default
        call (no voice/model override) succeeds on mlx-audio (:8890) with the HF
        repo id, and attempted_endpoints[0] records model='tts-1' against :8880."""
        async def fake_tts(**kwargs):
            if kwargs["tts_base_url"] == "http://127.0.0.1:8880/v1":
                raise ConnectionError("connection refused")
            if kwargs["tts_base_url"] == "http://127.0.0.1:8890/v1":
                assert kwargs["tts_model"] == "mlx-community/Kokoro-82M-bf16"
                return True, {"ttfa": 0.1}
            return False, None

        p1, p2, p3 = _resolver_patches()
        with p1, p2, p3, patch("voice_mode.core.text_to_speech", side_effect=fake_tts):
            success, metrics, config = await simple_tts_failover(
                text="hello", voice="af_sky", model=None
            )

        assert success
        assert config["base_url"] == "http://127.0.0.1:8890/v1"
        assert config["model"] == "mlx-community/Kokoro-82M-bf16"
        # The failed first attempt against :8880 recorded its own resolved model.
        assert config.get("attempted_endpoints") is None  # success -> no error list
        # Re-run capturing the attempted list by failing the mlx endpoint too:

    @pytest.mark.asyncio
    async def test_attempted_endpoints_carry_first_endpoint_model(self):
        """When :8880 fails, its attempted_endpoints entry shows model='tts-1'."""
        async def fake_tts(**kwargs):
            if kwargs["tts_base_url"] == "http://127.0.0.1:8880/v1":
                raise ConnectionError("connection refused")
            return False, None  # keep failing so the attempted list is populated

        p1, p2, p3 = _resolver_patches()
        with p1, p2, p3, patch("voice_mode.core.text_to_speech", side_effect=fake_tts):
            success, metrics, config = await simple_tts_failover(
                text="hello", voice="af_sky", model=None
            )

        assert not success
        first = config["attempted_endpoints"][0]
        assert first["endpoint"] == "http://127.0.0.1:8880/v1/audio/speech"
        assert first["model"] == "tts-1"


class TestClonePrepareEndpoint:
    """Clone voices bypass the resolver and keep their profile's model."""

    def test_clone_profile_model_untouched(self):
        """_prepare_tts_endpoint with a clone profile returns the profile's
        pinned model even against an mlx-audio endpoint (resolver not run)."""
        from types import SimpleNamespace

        clone_profile = SimpleNamespace(model="mlx-community/My-Clone-Voice")
        with patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}
        ):
            client, voice, model, provider_type = _prepare_tts_endpoint(
                base_url="http://127.0.0.1:8890/v1",
                voice="my_clone",
                model="tts-1",  # would resolve to the mlx default if consulted
                clone_profile=clone_profile,
            )
        assert model == "mlx-community/My-Clone-Voice"
        assert voice == "my_clone"
        assert provider_type == "mlx-audio"


class TestConverseNoModelCollapse:
    """converse.text_to_speech_with_failover must not collapse None -> TTS_MODELS[0]."""

    @pytest.mark.asyncio
    async def test_no_caller_model_passes_none_down(self):
        """With no caller model, model=None flows to simple_tts_failover so the
        per-provider resolver can pick per endpoint (VM-1390)."""
        from voice_mode.tools import converse as converse_mod

        captured = {}

        async def fake_failover(**kwargs):
            captured.update(kwargs)
            return True, {}, {}

        with patch(
            "voice_mode.simple_failover.simple_tts_failover", side_effect=fake_failover
        ), patch.object(converse_mod, "pronounce_enabled", return_value=False):
            await converse_mod.text_to_speech_with_failover(message="hello")

        assert "model" in captured
        assert captured["model"] is None

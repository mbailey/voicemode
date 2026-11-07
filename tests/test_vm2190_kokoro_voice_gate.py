"""VM-2190 — the resolver's provider-native gate consults the endpoints.

Regression for the af_nicole report (2026-08-30): from VM-1901's landing
(2026-07-25), ``resolve_voice()`` accepted a kokoro voice only if it was in
the 7-name ``KOKORO_MAPPED_VOICES`` whitelist or the user's
``VOICEMODE_VOICES`` — so 60 of the 67 kokoro voices raised ``Unresolvable``
while both local endpoints (kokoro-fastapi, mlx-audio) happily served them.

The fix: ``_is_provider_native`` also asks
``provider_discovery.known_provider_voices()`` — the union of what each
configured TTS endpoint claims (live registry data when discovered, the
registry's own seed lists otherwise). These tests pin both directions:
the full kokoro set resolves when a kokoro-family endpoint is configured,
and the gate still fails loudly when no configured endpoint can say the name.

No audio, no network: known_provider_voices() is sync and reads only
config.TTS_BASE_URLS plus the in-process registry dict, both patched here.
"""

import importlib

import pytest

from voice_mode import provider_discovery
from voice_mode.provider_discovery import EndpointInfo, KNOWN_KOKORO_VOICES


KOKORO_URL = "http://127.0.0.1:8880/v1"
MLX_URL = "http://127.0.0.1:8890/v1"
OPENAI_URL = "https://api.openai.com/v1"


def _reload_vp(voices_dir, monkeypatch):
    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices_dir))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)
    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)
    voice_profiles.load_profiles()
    return voice_profiles


def _set_endpoints(monkeypatch, urls, registry_tts=None):
    """Pin the two inputs known_provider_voices() reads.

    ``TTS_VOICES`` is pinned to a clone name so the resolver's config-list
    check (which runs before the endpoint check) can't accidentally pass a
    voice under test.
    """
    from voice_mode import config

    monkeypatch.setattr(config, "TTS_BASE_URLS", list(urls), raising=False)
    monkeypatch.setattr(config, "TTS_VOICES", ["laurie"], raising=False)
    monkeypatch.setattr(
        provider_discovery.provider_registry,
        "registry",
        {"tts": dict(registry_tts or {}), "stt": {}},
        raising=False,
    )


@pytest.fixture
def vp(tmp_path, monkeypatch):
    voices = tmp_path / "voices"
    voices.mkdir()  # no clone voices — provider path only
    return _reload_vp(voices, monkeypatch)


def test_af_nicole_resolves_with_kokoro_endpoint(vp, monkeypatch):
    """The reported regression: af_nicole must resolve, not raise."""
    _set_endpoints(monkeypatch, [KOKORO_URL, OPENAI_URL])
    res = vp.resolve_voice("af_nicole")
    assert res.kind == "provider"
    assert res.resolved == "af_nicole"
    assert res.via == "provider-native"


def test_full_kokoro_set_resolves_with_mlx_endpoint(vp, monkeypatch):
    """All 67 kokoro voices, not just the 7 OpenAI-mappable ones."""
    _set_endpoints(monkeypatch, [MLX_URL])
    for name in KNOWN_KOKORO_VOICES:
        res = vp.resolve_voice(name)
        assert res.kind == "provider", name
        assert res.resolved == name


def test_kokoro_voice_still_unresolvable_with_only_openai(vp, monkeypatch):
    """The gate is real: no configured endpoint can say af_nicole here.

    (af_sky et al. stay resolvable via KOKORO_MAPPED_VOICES — the
    OpenAI-equivalence table — which is exactly the designed distinction.)
    """
    _set_endpoints(monkeypatch, [OPENAI_URL])
    with pytest.raises(vp.Unresolvable):
        vp.resolve_voice("af_nicole")


def test_garbage_name_still_unresolvable(vp, monkeypatch):
    """VM-1901's headline guarantee survives the widened gate."""
    _set_endpoints(monkeypatch, [KOKORO_URL, MLX_URL, OPENAI_URL])
    with pytest.raises(vp.Unresolvable):
        vp.resolve_voice("definitely-not-a-real-voice")


def test_live_discovery_list_wins_over_seed(vp, monkeypatch):
    """A discovered (non-empty) voice list is respected verbatim."""
    info = EndpointInfo(
        base_url=KOKORO_URL,
        models=["tts-1"],
        voices=["custom_voice"],
        provider_type="kokoro",
    )
    _set_endpoints(monkeypatch, [KOKORO_URL], registry_tts={KOKORO_URL: info})

    res = vp.resolve_voice("custom_voice")
    assert res.kind == "provider"
    # ...and a seed-only name NOT in the live list no longer passes:
    with pytest.raises(vp.Unresolvable):
        vp.resolve_voice("af_nicole")


def test_empty_discovery_falls_back_to_seed(vp, monkeypatch):
    """mlx-audio has no voices endpoint, so a refresh stores voices=[] for
    it — the seed set must still apply or every voice goes dark again."""
    info = EndpointInfo(
        base_url=MLX_URL,
        models=["mlx-community/Kokoro-82M-bf16"],
        voices=[],
        provider_type="mlx-audio",
    )
    _set_endpoints(monkeypatch, [MLX_URL], registry_tts={MLX_URL: info})
    res = vp.resolve_voice("af_nicole")
    assert res.kind == "provider"
    assert res.resolved == "af_nicole"


def test_known_provider_voices_unions_all_endpoints(monkeypatch):
    """Direct contract check on the helper itself."""
    _set_endpoints(monkeypatch, [KOKORO_URL, OPENAI_URL])
    names = provider_discovery.known_provider_voices()
    assert "af_nicole" in names
    assert "alloy" in names
    assert "definitely-not-a-real-voice" not in names

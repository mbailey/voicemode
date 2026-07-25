"""VM-1901 fix-001 — resolver core: precedence, casts, dot-dirs, defensive raise.

Complements test_vm1901_alloy_fallback_repro.py (the five mouths) and
test_voice_profiles.py (loader/back-compat) with the design.md §9
acceptance-mapped tests that don't fit either of those files: multi-level
cast chains, dangling defaults, dot-dir invisibility (the phantom-voice
hazard design.md calls out), the file-selector/BadSelector precedence
branches, the provider-native whitelist being checked LAST, and the
defensive raise at simple_failover's OpenAI voice-mapping default arm.
"""

import importlib
import logging

import pytest


def _make_voice(parent, name, wav_bytes=b"riff", txt="transcript"):
    d = parent / name
    d.mkdir(parents=True)
    (d / "default.wav").write_bytes(wav_bytes)
    (d / "default.txt").write_text(txt)
    return d


def _reload(voices_dir, monkeypatch, **env):
    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices_dir))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)
    return voice_profiles


# ---------------------------------------------------------------------------
# Cast declaration + multi-level chains (design.md §4, §9 item 5)
# ---------------------------------------------------------------------------

class TestCastDeclaration:
    def test_declared_default_resolves(self, tmp_path, monkeypatch):
        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "peep-show/mark")
        _make_voice(voices, "peep-show/jez")
        (voices / "peep-show" / "voice.md").write_text("---\ndefault: mark\n---\n")

        vp = _reload(voices, monkeypatch)
        vp.load_profiles()
        res = vp.resolve_voice("peep-show")
        assert res.kind == "clone"
        assert res.resolved == "peep-show/mark"
        assert res.via == "cast-default:mark"

    def test_multi_level_chain_resolves_and_records_full_chain(self, tmp_path, monkeypatch):
        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "star-trek/tng/picard")
        _make_voice(voices, "star-trek/tng/riker")
        (voices / "star-trek" / "voice.md").write_text("---\ndefault: tng\n---\n")
        (voices / "star-trek" / "tng" / "voice.md").write_text("---\ndefault: picard\n---\n")

        vp = _reload(voices, monkeypatch)
        vp.load_profiles()
        res = vp.resolve_voice("star-trek")
        assert res.resolved == "star-trek/tng/picard"
        assert res.via == "cast-default:tng→picard"

    def test_dangling_default_raises_cast_default_missing_naming_members(self, tmp_path, monkeypatch):
        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "peep-show/mark")
        _make_voice(voices, "peep-show/jez")
        (voices / "peep-show" / "voice.md").write_text("---\ndefault: super-hans\n---\n")

        vp = _reload(voices, monkeypatch)
        vp.load_profiles()
        with pytest.raises(vp.CastDefaultMissing) as exc_info:
            vp.resolve_voice("peep-show")
        msg = str(exc_info.value)
        assert "super-hans" in msg
        assert "mark" in msg and "jez" in msg

    def test_group_level_voice_md_does_not_interfere_with_transcripts(self, tmp_path, monkeypatch):
        """A group's voice.md has no `transcript:` key — must never leak
        into a member voice's transcript resolution."""
        voices = tmp_path / "voices"
        voices.mkdir()
        mark_dir = _make_voice(voices, "peep-show/mark")
        (voices / "peep-show" / "voice.md").write_text("---\ndefault: mark\n---\n")

        vp = _reload(voices, monkeypatch)
        vp.load_profiles()
        profile = vp.get_profile("peep-show/mark")
        assert profile.ref_text == "transcript"  # from mark's own default.txt


# ---------------------------------------------------------------------------
# Dot-dirs invisible to the loader (design.md §3.3 — phantom-voice hazard)
# ---------------------------------------------------------------------------

class TestDotDirsInvisible:
    def test_dot_dir_under_a_group_never_registers_phantom_voices(self, tmp_path, monkeypatch, caplog):
        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "aubrey-plaza")
        # A hidden metadata dir holding something that WOULD look like a
        # voice if the walk ever descended into it.
        phantom = voices / "aubrey-plaza" / ".samples" / "phantom"
        phantom.mkdir(parents=True)
        (phantom / "default.wav").write_bytes(b"ghost")

        vp = _reload(voices, monkeypatch)
        profiles = vp.load_profiles()
        assert "phantom" not in profiles
        assert "aubrey-plaza/.samples/phantom" not in profiles
        with pytest.raises(vp.Unresolvable):
            vp.resolve_voice("phantom")

    def test_dot_dir_group_never_walked(self, tmp_path, monkeypatch):
        """A dot-prefixed GROUP directory (not just a dot-dir under a voice)
        is also never walked."""
        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, ".hidden-cast/someone")

        vp = _reload(voices, monkeypatch)
        profiles = vp.load_profiles()
        assert profiles == {}
        with pytest.raises(vp.Unresolvable):
            vp.resolve_voice("someone")


# ---------------------------------------------------------------------------
# Voice-with-unreachable-subdir lint (design.md §3.3)
# ---------------------------------------------------------------------------

def test_voice_with_visible_voicelike_subdir_gets_load_time_lint(tmp_path, monkeypatch, caplog):
    voices = tmp_path / "voices"
    voices.mkdir()
    sam = _make_voice(voices, "samantha")
    nested = sam / "understudy"
    nested.mkdir()
    (nested / "default.wav").write_bytes(b"d")

    vp = _reload(voices, monkeypatch)
    with caplog.at_level(logging.WARNING, logger="voicemode"):
        profiles = vp.load_profiles()

    assert set(profiles.keys()) == {"samantha"}  # understudy never registers
    assert any(
        "samantha" in r.message and "understudy" in r.message and "unreachable" in r.message.lower()
        for r in caplog.records
    )


# ---------------------------------------------------------------------------
# Segment walk: group-qualified file selector + BadSelector (design.md §3.2.4)
# ---------------------------------------------------------------------------

class TestSegmentWalkSelectors:
    def test_group_qualified_file_selector_resolves(self, tmp_path, monkeypatch):
        voices = tmp_path / "voices"
        voices.mkdir()
        mark_dir = _make_voice(voices, "peep-show/mark")
        (mark_dir / "angry.wav").write_bytes(b"angry")
        (mark_dir / "angry.txt").write_text("angry transcript")

        vp = _reload(voices, monkeypatch)
        vp.load_profiles()
        res = vp.resolve_voice("peep-show/mark/angry.wav")
        assert res.kind == "clone"
        assert res.profile.ref_audio.endswith("/peep-show/mark/angry.wav")
        assert res.profile.ref_text == "angry transcript"

    def test_two_segment_selector_after_a_voice_is_bad_selector(self, tmp_path, monkeypatch):
        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "samantha")

        vp = _reload(voices, monkeypatch)
        vp.load_profiles()
        with pytest.raises(vp.BadSelector):
            vp.resolve_voice("samantha/deep/extra.wav")

    def test_group_qualified_index_composes(self, tmp_path, monkeypatch):
        voices = tmp_path / "voices"
        voices.mkdir()
        bob = _make_voice(voices, "bobs-burgers/bob")
        (bob / "angry.wav").write_bytes(b"a")
        (bob / "angry.txt").write_text("angry")

        vp = _reload(voices, monkeypatch)
        vp.load_profiles()
        res = vp.resolve_voice("bobs-burgers/bob[0]")
        assert res.resolved == "bobs-burgers/bob"
        assert res.profile.ref_audio.endswith("/angry.wav")

    def test_no_meaning_for_colon_form_even_when_qualified(self, tmp_path, monkeypatch):
        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "aubrey-plaza")

        vp = _reload(voices, monkeypatch)
        vp.load_profiles()
        with pytest.raises(vp.Unresolvable):
            vp.resolve_voice("aubrey-plaza:0")


# ---------------------------------------------------------------------------
# Ambiguity across groups (design.md §3.2.5c)
# ---------------------------------------------------------------------------

def test_ambiguous_group_leaf_lists_both_qualified_forms(tmp_path, monkeypatch):
    """Two GROUPS (not voices) sharing a leaf name — "narrator" names a
    container in both franchises, each with its own member(s). Ambiguous at
    the group level, distinct from mouth 3's voice-leaf collision."""
    voices = tmp_path / "voices"
    voices.mkdir()
    _make_voice(voices, "franchise-x/narrator/alt-take")
    _make_voice(voices, "franchise-y/narrator/other-take")

    vp = _reload(voices, monkeypatch)
    vp.load_profiles()
    with pytest.raises(vp.AmbiguousLeaf) as exc_info:
        vp.resolve_voice("narrator")
    msg = str(exc_info.value)
    assert "franchise-x/narrator" in msg
    assert "franchise-y/narrator" in msg


def test_voice_wins_over_group_when_leaf_is_unique_among_voices(tmp_path, monkeypatch):
    """design.md: 'concrete beats container' — a voice leaf that's unique
    resolves even if a same-named GROUP also exists somewhere."""
    voices = tmp_path / "voices"
    voices.mkdir()
    _make_voice(voices, "blackadder/blackadder")  # voice leaf "blackadder"
    _make_voice(voices, "blackadder/baldrick")

    vp = _reload(voices, monkeypatch)
    vp.load_profiles()
    res = vp.resolve_voice("blackadder")
    assert res.kind == "clone"
    assert res.resolved == "blackadder/blackadder"
    assert res.via == "leaf"


# ---------------------------------------------------------------------------
# Provider-native whitelist checked LAST (design.md §3.2.6)
# ---------------------------------------------------------------------------

def test_provider_native_whitelist_checked_last_and_explicitly(tmp_path, monkeypatch):
    voices = tmp_path / "voices"
    voices.mkdir()  # no clone voices at all

    vp = _reload(voices, monkeypatch)
    vp.load_profiles()
    for name in ("alloy", "echo", "fable", "nova", "onyx", "shimmer"):
        res = vp.resolve_voice(name)
        assert res.kind == "provider"
        assert res.resolved == name
        assert res.via == "provider-native"


def test_unknown_name_never_reaches_provider_whitelist_silently(tmp_path, monkeypatch):
    voices = tmp_path / "voices"
    voices.mkdir()

    vp = _reload(voices, monkeypatch)
    vp.load_profiles()
    with pytest.raises(vp.Unresolvable):
        vp.resolve_voice("definitely-not-a-real-voice")


# ---------------------------------------------------------------------------
# Undeclared-group severity switch (fix-001 description; design.md §7 fence)
# ---------------------------------------------------------------------------

class TestUndeclaredGroupSeverity:
    def test_default_is_error(self, tmp_path, monkeypatch):
        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "blackadder/edmund")
        _make_voice(voices, "blackadder/baldrick")

        vp = _reload(voices, monkeypatch)
        vp.load_profiles()
        with pytest.raises(vp.NotACast):
            vp.resolve_voice("blackadder")

    def test_warn_mode_resolves_arbitrarily_and_logs(self, tmp_path, monkeypatch, caplog):
        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "blackadder/edmund")
        _make_voice(voices, "blackadder/baldrick")

        vp = _reload(voices, monkeypatch, VOICEMODE_CAST_UNDECLARED_SEVERITY="warn")
        vp.load_profiles()
        with caplog.at_level(logging.WARNING, logger="voicemode"):
            res = vp.resolve_voice("blackadder")
        # Alphabetically-first member — deterministic, documented, never a
        # different provider's voice (the blast radius stays inside the cast).
        assert res.resolved == "blackadder/baldrick"
        assert "undeclared" in res.via
        assert any("blackadder" in r.message and "warn" in r.message.lower() for r in caplog.records)

    def test_warn_mode_never_reaches_a_different_provider(self, tmp_path, monkeypatch):
        """Belt-and-braces: even the escape hatch never crosses providers —
        it stays inside the cast's own clone endpoint."""
        from voice_mode.simple_failover import _prepare_tts_endpoint, _resolve_tts_endpoints

        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "blackadder/edmund")
        _make_voice(voices, "blackadder/baldrick")

        vp = _reload(voices, monkeypatch, VOICEMODE_CAST_UNDECLARED_SEVERITY="warn")
        vp.load_profiles()

        import voice_mode.simple_failover as sf
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sf, "TTS_BASE_URLS", ["https://api.openai.com/v1"])
            endpoints, clone_profile = _resolve_tts_endpoints("blackadder", None)
            assert clone_profile is not None
            _client, _voice, _model, provider_type = _prepare_tts_endpoint(
                endpoints[0], "blackadder", None, clone_profile
            )
        assert provider_type != "openai"


# ---------------------------------------------------------------------------
# Defensive raise at simple_failover's OpenAI mapping default arm
# (design.md §3.2.7 "belt to P1's braces")
# ---------------------------------------------------------------------------

def test_unmapped_provider_voice_raises_instead_of_defaulting_to_alloy():
    from voice_mode.simple_failover import _prepare_tts_endpoint, UnmappedProviderVoiceError

    # A name that reaches the OpenAI endpoint's mapping table unrecognised —
    # simulates upstream drift (resolver whitelist grew, this table didn't).
    with pytest.raises(UnmappedProviderVoiceError):
        _prepare_tts_endpoint(
            base_url="https://api.openai.com/v1",
            voice="some-future-kokoro-voice",
            model="tts-1",
            clone_profile=None,
        )


def test_known_kokoro_voice_still_maps_cleanly_on_openai_endpoint():
    from voice_mode.simple_failover import _prepare_tts_endpoint

    _client, selected_voice, _model, provider_type = _prepare_tts_endpoint(
        base_url="https://api.openai.com/v1",
        voice="af_sky",
        model="tts-1",
        clone_profile=None,
    )
    assert selected_voice == "nova"
    assert provider_type == "openai"


def test_resolution_failure_never_crashes_the_caller_returns_clean_failure(tmp_path, monkeypatch):
    """simple_tts_failover/synthesize must not let a VoiceResolutionError
    propagate as a bare, unhandled exception — converse() expects a
    (success, metrics, config) tuple to report the error through."""
    import asyncio

    from voice_mode.simple_failover import simple_tts_failover

    voices = tmp_path / "voices"
    voices.mkdir()
    _reload(voices, monkeypatch)

    async def _run():
        return await simple_tts_failover(text="hello", voice="not-a-real-voice")

    success, metrics, config = asyncio.run(_run())
    assert success is False
    assert config["error_type"] == "voice_resolution_failed"
    assert "not-a-real-voice" in config["error"]
    assert config["attempted_endpoints"] == []

"""VM-1901 — deliberate repro of every silent-substitution mouth (repro-001).

Reported symptom (README.md): an unresolvable ``voice=`` reference in
``converse()`` silently synthesizes with **OpenAI Alloy** (a cross-provider
identity swap) instead of erroring or falling back to the *named* voice's own
default clip. The tool result still reports success; nothing in the log
calls out the substitution as a failure.

Per triage-001's verdict, this is not one bug but a *family* of resolver
mouths that all share the same failure shape (voice_profiles.get_profile()
returns ``None`` -> ``is_clone_voice()`` is ``False`` -> ``simple_failover``
falls through to the generic ``TTS_BASE_URLS`` chain -> if that chain reaches
OpenAI, ``_prepare_tts_endpoint`` maps any name it doesn't recognise to
``"alloy"`` with only an INFO log line). This file exercises **five** mouths
individually, plus the original 2026-07-09 colon-syntax finding, each as a
deterministic, recorded repro: what was NOT logged, and what the call
actually returns.

MOUTH 1 — bare container (``secretary``, ``blackadder``)
MOUTH 2 — group-qualified path (``secretary/lee-holloway``)
MOUTH 3 — leaf-name collision (two dirs sharing a leaf name)
MOUTH 4 — sample-bin dir (>=2 wavs, no default.wav)
MOUTH 5 — out-of-range index (``name[99]``)
SYNTAX  — colon selector (``aubrey-plaza:2``) is not implemented; the
          bracket form (``aubrey-plaza[2]``) is, confirming this is a syntax
          gap, not (only) a resolver bug.

Nothing here is fixed yet — every assertion below documents *current*,
pre-fix behaviour. design-001/fix-001 change these.
"""

import importlib
import logging

import pytest

from voice_mode.simple_failover import _prepare_tts_endpoint, _resolve_tts_endpoints


OPENAI_URL = "https://api.openai.com/v1"


def _make_voice(parent, name, wav_bytes=b"riff", txt="transcript"):
    """Drop a ``default.wav`` + ``default.txt`` voice dir under ``parent``."""
    d = parent / name
    d.mkdir(parents=True)
    (d / "default.wav").write_bytes(wav_bytes)
    (d / "default.txt").write_text(txt)
    return d


def _reload_voice_profiles(voices_dir, monkeypatch):
    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices_dir))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)
    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)
    return voice_profiles


def _hits_alloy(voice_expr, vp_module):
    """Drive the real resolver + endpoint-prep pipeline for ``voice_expr``.

    Mirrors what ``simple_tts_failover``/``simple_tts_synthesize`` do: resolve
    endpoints (clone route vs generic chain), then prepare the first endpoint
    exactly as the failover loop would. Returns the ``selected_voice`` that
    would actually be sent to the wire, plus whether it counted as a clone
    voice at all.
    """
    import voice_mode.simple_failover as sf

    # simple_failover imports get_profile/is_clone_voice lazily from
    # voice_mode.voice_profiles inside _resolve_tts_endpoints, so reloading
    # the voice_profiles module (fixture above) is picked up without also
    # reloading simple_failover.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sf, "TTS_BASE_URLS", [OPENAI_URL])
        endpoints, clone_profile = _resolve_tts_endpoints(voice_expr, None)
        _client, selected_voice, _model, provider_type = _prepare_tts_endpoint(
            endpoints[0], voice_expr, None, clone_profile
        )
    return selected_voice, provider_type, clone_profile is not None


# ---------------------------------------------------------------------------
# MOUTH 1 — bare container: voice="blackadder" / voice="secretary"
# ---------------------------------------------------------------------------

@pytest.fixture
def container_voices_dir(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    # secretary/ has exactly one child -> unambiguous, still not exposed today
    _make_voice(voices, "secretary/lee-holloway")
    # blackadder/ has two children -> ambiguous either way. Neither child
    # shares the container's own name, so "blackadder" the container never
    # coincidentally resolves via a same-named leaf.
    _make_voice(voices, "blackadder/edmund")
    _make_voice(voices, "blackadder/baldrick")
    return voices


class TestMouth1BareContainer:
    """FAVORITES.md-documented names like ``secretary``/``blackadder`` name a
    container dir, not a voice — today that resolves to nothing, silently."""

    def test_container_name_is_not_a_registered_profile(
        self, container_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        profiles = vp.load_profiles()
        # The container names themselves never register — only their leaves do.
        assert "secretary" not in profiles
        assert "blackadder" not in profiles
        assert {"lee-holloway", "edmund", "baldrick"} <= set(profiles.keys())

    def test_container_name_is_not_recognised_as_a_clone_voice(
        self, container_voices_dir, monkeypatch, caplog
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()
        with caplog.at_level(logging.DEBUG, logger="voicemode"):
            secretary_is_clone = vp.is_clone_voice("secretary")
            blackadder_is_clone = vp.is_clone_voice("blackadder")
        assert secretary_is_clone is False
        assert blackadder_is_clone is False
        # The damning bit: is_clone_voice() emits NO log line at all for an
        # unresolvable name — the caller gets a bare False with zero breadcrumb.
        assert caplog.records == []

    @pytest.mark.parametrize("expr", ["secretary", "blackadder"])
    def test_container_name_silently_lands_on_alloy(
        self, container_voices_dir, monkeypatch, expr
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()
        selected_voice, provider_type, was_clone = _hits_alloy(expr, vp)
        # Requested `expr` (a real, populated container of clone voices);
        # got: OpenAI Alloy. No exception, no error surfaced to the caller.
        assert was_clone is False
        assert provider_type == "openai"
        assert selected_voice == "alloy"


# ---------------------------------------------------------------------------
# MOUTH 2 — group-qualified path: voice="secretary/lee-holloway"
# ---------------------------------------------------------------------------

class TestMouth2GroupQualifiedPath:
    """FAVORITES.md writes the group-qualified form ``secretary/lee-holloway``
    to disambiguate — that form fails today, while the bare leaf name works,
    because ``parse_voice_expr`` partitions on ``/`` and treats the tail as a
    *file* inside a voice dir named by the head, not as a nested profile
    lookup."""

    def test_parse_treats_slash_as_file_selector_not_group_path(
        self, container_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        assert vp.parse_voice_expr("secretary/lee-holloway") == (
            "secretary",
            "lee-holloway",
        )

    def test_group_qualified_path_fails_while_bare_leaf_works(
        self, container_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()

        # The documented form: fails (head "secretary" is not a profile).
        assert vp.get_profile("secretary/lee-holloway") is None
        assert vp.is_clone_voice("secretary/lee-holloway") is False

        # The bare leaf name: works fine.
        assert vp.get_profile("lee-holloway") is not None
        assert vp.is_clone_voice("lee-holloway") is True

    def test_group_qualified_path_silently_lands_on_alloy(
        self, container_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()
        selected_voice, provider_type, was_clone = _hits_alloy(
            "secretary/lee-holloway", vp
        )
        assert was_clone is False
        assert provider_type == "openai"
        assert selected_voice == "alloy"


# ---------------------------------------------------------------------------
# MOUTH 3 — leaf-name collision: two dirs sharing a leaf name
# ---------------------------------------------------------------------------

@pytest.fixture
def collision_voices_dir(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    _make_voice(voices, "bobs-burgers/bob")
    _make_voice(voices, "the-simpsons/bob")  # collides on leaf "bob"
    _make_voice(voices, "alan")  # unaffected control
    return voices


class TestMouth3LeafCollision:
    """voice_profiles.py:277-283 — two same-named leaves anywhere in the tree
    drop ALL candidates. Unlike the other mouths, load-time DOES log an
    ERROR (once, at startup) — but the per-call resolve path is exactly as
    silent as the rest: no exception, straight through to Alloy."""

    def test_collision_drops_both_candidates_with_one_load_time_error(
        self, collision_voices_dir, monkeypatch, caplog
    ):
        vp = _reload_voice_profiles(collision_voices_dir, monkeypatch)
        with caplog.at_level(logging.ERROR, logger="voicemode"):
            profiles = vp.load_profiles()
        assert "bob" not in profiles
        assert "alan" in profiles
        assert any("collision" in r.message.lower() for r in caplog.records)

    def test_collision_resolve_call_has_no_error_of_its_own(
        self, collision_voices_dir, monkeypatch, caplog
    ):
        vp = _reload_voice_profiles(collision_voices_dir, monkeypatch)
        vp.load_profiles()  # the one-time collision ERROR already fired here
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="voicemode"):
            is_clone = vp.is_clone_voice("bob")
        assert is_clone is False
        # The per-call check itself is silent — the only signal already
        # scrolled off at startup, long before this converse() call happens.
        assert caplog.records == []

    def test_collision_silently_lands_on_alloy(self, collision_voices_dir, monkeypatch):
        vp = _reload_voice_profiles(collision_voices_dir, monkeypatch)
        vp.load_profiles()
        selected_voice, provider_type, was_clone = _hits_alloy("bob", vp)
        assert was_clone is False
        assert provider_type == "openai"
        assert selected_voice == "alloy"


# ---------------------------------------------------------------------------
# MOUTH 4 — sample-bin dir: >=2 wavs, no default.wav
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_bin_voices_dir(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    mixtape = voices / "mixtape"
    mixtape.mkdir()
    (mixtape / "take-1.wav").write_bytes(b"riff-1")
    (mixtape / "take-2.wav").write_bytes(b"riff-2")
    # No default.wav — voice_profiles.py:104-109 treats this as a sample
    # bin, not a voice, and skips it entirely (debug-only log, no ERROR).
    return voices


class TestMouth4SampleBinDir:
    def test_sample_bin_dir_never_registers_as_a_voice(
        self, sample_bin_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(sample_bin_voices_dir, monkeypatch)
        profiles = vp.load_profiles()
        assert "mixtape" not in profiles

    def test_sample_bin_dir_skip_is_debug_only(
        self, sample_bin_voices_dir, monkeypatch, caplog
    ):
        vp = _reload_voice_profiles(sample_bin_voices_dir, monkeypatch)
        with caplog.at_level(logging.INFO, logger="voicemode"):
            vp.load_profiles()
        # Nothing at INFO-or-louder mentions the skip — you'd have to already
        # be running at DEBUG to see why "mixtape" never showed up.
        assert not any("mixtape" in r.message for r in caplog.records)

    def test_sample_bin_dir_silently_lands_on_alloy(
        self, sample_bin_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(sample_bin_voices_dir, monkeypatch)
        vp.load_profiles()
        selected_voice, provider_type, was_clone = _hits_alloy("mixtape", vp)
        assert was_clone is False
        assert provider_type == "openai"
        assert selected_voice == "alloy"


# ---------------------------------------------------------------------------
# MOUTH 5 — out-of-range index: voice="name[99]"
# ---------------------------------------------------------------------------

@pytest.fixture
def indexed_voices_dir(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    sam = voices / "samantha"
    sam.mkdir()
    (sam / "default.wav").write_bytes(b"riff-default")
    (sam / "default.txt").write_text("default transcript")
    (sam / "angry.wav").write_bytes(b"riff-angry")
    (sam / "angry.txt").write_text("angry transcript")
    return voices


class TestMouth5OutOfRangeIndex:
    """Distinct shape from the other four: this mouth does NOT reach Alloy —
    ``resolve_voice_expr`` catches the bad index and falls back to the SAME
    voice's default.wav. It logs an ERROR (unlike mouths 1/2/3's per-call
    silence) but still returns success with the wrong *clip*, not the wrong
    *voice* — worth recording precisely because it's the one mouth that
    partially self-corrects."""

    def test_out_of_range_index_logs_error_but_returns_default_clip(
        self, indexed_voices_dir, monkeypatch, caplog
    ):
        vp = _reload_voice_profiles(indexed_voices_dir, monkeypatch)
        vp.load_profiles()
        with caplog.at_level(logging.ERROR, logger="voicemode"):
            p = vp.get_profile("samantha[99]")
        assert p is not None
        assert p.ref_audio.endswith("/samantha/default.wav")
        assert any("out of range" in r.message.lower() for r in caplog.records)

    def test_out_of_range_index_does_not_cross_providers(
        self, indexed_voices_dir, monkeypatch
    ):
        """Unlike mouths 1-4, this one stays a clone voice end to end — it
        never reaches OpenAI/Alloy. Recorded here so fix-001 doesn't
        conflate this mouth's (smaller) blast radius with the others'."""
        vp = _reload_voice_profiles(indexed_voices_dir, monkeypatch)
        vp.load_profiles()
        selected_voice, provider_type, was_clone = _hits_alloy(
            "samantha[99]", vp
        )
        assert was_clone is True
        assert provider_type != "openai"
        assert selected_voice == "samantha[99]"


# ---------------------------------------------------------------------------
# SYNTAX FINDING — colon selector not implemented (2026-07-09 original repro)
# ---------------------------------------------------------------------------

@pytest.fixture
def aubrey_plaza_voices_dir(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    ap = voices / "aubrey-plaza"
    ap.mkdir()
    (ap / "default.wav").write_bytes(b"riff-default")
    (ap / "default.txt").write_text("default transcript")
    (ap / "next-question.wav").write_bytes(b"riff-nq")
    (ap / "next-question.txt").write_text("next question transcript")
    return voices


class TestColonSyntaxNotImplemented:
    """The ORIGINAL 2026-07-09 repro: ``voice="aubrey-plaza:2"`` and
    ``voice="aubrey-plaza:next-question"`` fell through to Alloy. This
    confirms *why*: ``name:N``/``name:label`` (SuperDirt-style colon, per
    voices/README.md rule 7) is simply not parsed anywhere — the whole
    string is treated as a literal (and unregistered) voice name. The
    bracket form ``name[N]`` IS implemented and works. This is a syntax
    gap, layered on top of (not instead of) the resolver-silence bug."""

    def test_colon_form_is_parsed_as_a_single_opaque_name(
        self, aubrey_plaza_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(aubrey_plaza_voices_dir, monkeypatch)
        assert vp.parse_voice_expr("aubrey-plaza:2") == ("aubrey-plaza:2", None)
        assert vp.parse_voice_expr("aubrey-plaza:next-question") == (
            "aubrey-plaza:next-question",
            None,
        )

    def test_colon_form_is_unresolvable_bracket_form_works(
        self, aubrey_plaza_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(aubrey_plaza_voices_dir, monkeypatch)
        vp.load_profiles()

        assert vp.get_profile("aubrey-plaza:2") is None
        assert vp.is_clone_voice("aubrey-plaza:2") is False
        assert vp.get_profile("aubrey-plaza:next-question") is None
        assert vp.is_clone_voice("aubrey-plaza:next-question") is False

        # The documented, working alternative:
        indexed = vp.get_profile("aubrey-plaza[0]")
        assert indexed is not None
        assert indexed.ref_audio.endswith(".wav")

    def test_colon_form_silently_lands_on_alloy(
        self, aubrey_plaza_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(aubrey_plaza_voices_dir, monkeypatch)
        vp.load_profiles()
        selected_voice, provider_type, was_clone = _hits_alloy(
            "aubrey-plaza:2", vp
        )
        assert was_clone is False
        assert provider_type == "openai"
        assert selected_voice == "alloy"
        # ...exactly the field-observed 2026-07-09 symptom, reproduced
        # deterministically and in-process.

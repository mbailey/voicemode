"""VM-1901 — every silent-substitution mouth, before AND after the fix.

Originally filed (repro-001) as a deliberate repro of the reported symptom:
an unresolvable ``voice=`` reference in ``converse()`` silently synthesizes
with **OpenAI Alloy** (a cross-provider identity swap) instead of erroring
or falling back to the *named* voice's own default clip — with the tool
result still reporting success and nothing in the log calling out the
substitution.

fix-001 closes every one of these mouths by making voice resolution TOTAL
(:func:`voice_mode.voice_profiles.resolve_voice`): an unresolvable
expression now RAISES — before any TTS endpoint is tried, never reaching a
provider at all — instead of silently falling through to
``voice_mapping.get(voice, "alloy")``. This file is the evidence base for
that fix: every assertion below now documents the POST-fix behaviour
(a loud, specific exception naming the alternatives), with the pre-fix
symptom kept in the docstrings so the regression this closes stays legible.

MOUTH 1 — bare container (``secretary``, ``blackadder``) -> now a NotACast
          (undeclared group) error naming the members, not Alloy.
MOUTH 2 — group-qualified path (``secretary/lee-holloway``) -> now RESOLVES
          (closes the FAVORITES.md:27 doc/code lie).
MOUTH 3 — leaf-name collision -> both qualified forms now resolve; the bare,
          ambiguous form raises AmbiguousLeaf naming them.
MOUTH 4 — sample-bin dir (>=2 wavs, no default.wav) -> the skip is now
          WARNING-visible at load, and naming the dir directly raises
          Unresolvable (it registers as neither a voice nor a group).
MOUTH 5 — out-of-range index (``name[99]``) -> now raises IndexOutOfRange
          naming the count, instead of silently falling back to
          default.wav. (Design.md ruled this mouth severable/lower-severity
          since it never crossed providers — fix-001 closes it anyway since
          the resolver core makes it "free": no separate code path.)
SYNTAX  — colon selector (``aubrey-plaza:2``) is reserved, not implemented
          (voices/README.md rule 7 says "future"); it's just an opaque,
          unresolvable name — confirmed via the bracket form working.
"""

import importlib
import logging

import pytest

from voice_mode.simple_failover import _prepare_tts_endpoint, _resolve_tts_endpoints

# NOTE: exception classes are deliberately NOT imported at module level.
# Every test reloads voice_mode.voice_profiles (via _reload_voice_profiles)
# to pick up a fresh VOICEMODE_VOICES_DIR, and importlib.reload() rebinds
# each class name to a NEW class object — a module-level import taken before
# the first reload would go stale and silently fail isinstance()/except
# checks against later-raised instances. Always reach for exception classes
# off the reloaded module (``vp.NotACast``, etc.), never a bare import.


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


def _never_reaches_wire(voice_expr, vp_module):
    """Drive the REAL endpoint-resolution entry point for ``voice_expr`` and
    assert it raises before any endpoint/model is selected — i.e. no TTS
    request could possibly be issued and no cross-provider substitution is
    possible. Mirrors what ``simple_tts_failover``/``simple_tts_synthesize``
    do first, before touching ``_prepare_tts_endpoint``. Returns the raised
    exception for message inspection.
    """
    import voice_mode.simple_failover as sf

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sf, "TTS_BASE_URLS", [OPENAI_URL])
        with pytest.raises(vp_module.VoiceResolutionError) as exc_info:
            _resolve_tts_endpoints(voice_expr, None)
    return exc_info.value


def _resolves_to_clone(voice_expr, vp_module):
    """Drive the real resolver + endpoint-prep pipeline for ``voice_expr``,
    asserting it resolves as a CLONE voice (never reaching the provider
    chain / Alloy). Returns the selected_voice, provider_type, clone_profile.
    """
    import voice_mode.simple_failover as sf

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sf, "TTS_BASE_URLS", [OPENAI_URL])
        endpoints, clone_profile, _resolution = _resolve_tts_endpoints(voice_expr, None)
        assert clone_profile is not None
        _client, selected_voice, _model, provider_type, _is_fallback, _fallback_reason = _prepare_tts_endpoint(
            endpoints[0], voice_expr, None, clone_profile
        )
    return selected_voice, provider_type, clone_profile


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
    container (group) dir, not a voice. Pre-fix, that resolved to nothing
    and silently landed on Alloy. Post-fix: an undeclared group is a
    ``NotACast`` — a cast requires a DECLARED default (Mike's ruling,
    2026-07-25) — and the error names every member."""

    def test_container_registers_as_a_group_not_a_voice_profile(
        self, container_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        profiles = vp.load_profiles()
        # The container names themselves never register as VOICE profiles —
        # only their (now canonically-keyed) qualified leaves do.
        assert "secretary" not in profiles
        assert "blackadder" not in profiles
        assert {"secretary/lee-holloway", "blackadder/edmund", "blackadder/baldrick"} <= set(
            profiles.keys()
        )

    def test_container_name_is_not_recognised_as_a_clone_voice(
        self, container_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()
        # is_clone_voice() keeps its old best-effort contract: an undeclared
        # cast isn't a clone voice, but this wrapper stays silent (False) by
        # design — callers that need the loud failure use resolve_voice()
        # directly, exercised below.
        assert vp.is_clone_voice("secretary") is False
        assert vp.is_clone_voice("blackadder") is False

    @pytest.mark.parametrize("expr,members", [
        ("secretary", ["lee-holloway"]),
        ("blackadder", ["baldrick", "edmund"]),
    ])
    def test_undeclared_container_raises_not_a_cast_naming_members(
        self, container_voices_dir, monkeypatch, expr, members
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()
        with pytest.raises(vp.NotACast) as exc_info:
            vp.resolve_voice(expr)
        msg = str(exc_info.value)
        for member in members:
            assert member in msg

    @pytest.mark.parametrize("expr", ["secretary", "blackadder"])
    def test_container_name_raises_before_any_endpoint_is_tried(
        self, container_voices_dir, monkeypatch, expr
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()
        exc = _never_reaches_wire(expr, vp)
        assert isinstance(exc, vp.NotACast)
        # This IS the fix: no exception, no error surfaced was the old bug.
        # Now it's a loud, specific, pre-wire failure — never Alloy.

    def test_declared_cast_resolves_to_its_default_member(
        self, container_voices_dir, monkeypatch
    ):
        """Once a group DECLARES a default (voice.md `default:`), it's a
        cast and resolves — Mike's ruling: casts are first-class, not an
        error case."""
        (container_voices_dir / "secretary" / "voice.md").write_text(
            "---\ndefault: lee-holloway\n---\n"
        )
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()
        res = vp.resolve_voice("secretary")
        assert res.kind == "clone"
        assert res.resolved == "secretary/lee-holloway"
        assert res.via == "cast-default:lee-holloway"


# ---------------------------------------------------------------------------
# MOUTH 2 — group-qualified path: voice="secretary/lee-holloway"
# ---------------------------------------------------------------------------

class TestMouth2GroupQualifiedPath:
    """FAVORITES.md writes the group-qualified form ``secretary/lee-holloway``
    to disambiguate. Pre-fix that form failed (parse_voice_expr partitioned
    on ``/`` and treated the tail as a *file* inside a voice dir named by the
    head). Post-fix: resolve_voice() walks the actual tree segment by
    segment, so the qualified form resolves — closing the one genuine
    doc/code lie in this task."""

    def test_legacy_parser_still_treats_slash_as_file_selector(
        self, container_voices_dir, monkeypatch
    ):
        """parse_voice_expr() is kept, unchanged, for back-compat callers —
        resolve_voice() no longer calls it. Documented here so nobody is
        surprised the two functions disagree about ``/``."""
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        assert vp.parse_voice_expr("secretary/lee-holloway") == (
            "secretary",
            "lee-holloway",
        )

    def test_group_qualified_path_now_resolves(
        self, container_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()

        # The documented form now resolves (mouth 2, closed):
        p = vp.get_profile("secretary/lee-holloway")
        assert p is not None
        assert p.ref_audio.endswith("/secretary/lee-holloway/default.wav")
        assert vp.is_clone_voice("secretary/lee-holloway") is True

        # The bare leaf name still works too (unambiguous):
        assert vp.get_profile("lee-holloway") is not None
        assert vp.is_clone_voice("lee-holloway") is True

    def test_group_qualified_path_reaches_the_named_clone_never_alloy(
        self, container_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(container_voices_dir, monkeypatch)
        vp.load_profiles()
        selected_voice, provider_type, clone_profile = _resolves_to_clone(
            "secretary/lee-holloway", vp
        )
        assert provider_type != "openai"
        assert clone_profile.ref_audio.endswith("/secretary/lee-holloway/default.wav")


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
    """voice_profiles.py — two same-named leaves anywhere in the tree used
    to drop ALL candidates at load time (one ERROR) and then resolve calls
    were silent (straight through to Alloy). Post-fix: BOTH qualified forms
    register and resolve; only the bare, ambiguous name fails, loudly,
    naming the qualified alternatives — strictly better on both halves."""

    def test_collision_registers_both_qualified_forms_with_a_load_time_warning(
        self, collision_voices_dir, monkeypatch, caplog
    ):
        vp = _reload_voice_profiles(collision_voices_dir, monkeypatch)
        with caplog.at_level(logging.WARNING, logger="voicemode"):
            profiles = vp.load_profiles()
        assert "bobs-burgers/bob" in profiles
        assert "the-simpsons/bob" in profiles
        assert "alan" in profiles
        assert any("ambiguous" in r.message.lower() and "bob" in r.message for r in caplog.records)

    def test_bare_ambiguous_name_raises_at_resolve_time(
        self, collision_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(collision_voices_dir, monkeypatch)
        vp.load_profiles()
        with pytest.raises(vp.AmbiguousLeaf) as exc_info:
            vp.resolve_voice("bob")
        msg = str(exc_info.value)
        assert "bobs-burgers/bob" in msg
        assert "the-simpsons/bob" in msg

    def test_collision_raises_before_any_endpoint_is_tried(self, collision_voices_dir, monkeypatch):
        vp = _reload_voice_profiles(collision_voices_dir, monkeypatch)
        vp.load_profiles()
        exc = _never_reaches_wire("bob", vp)
        assert isinstance(exc, vp.AmbiguousLeaf)

    def test_each_qualified_form_resolves_to_its_own_clone(self, collision_voices_dir, monkeypatch):
        vp = _reload_voice_profiles(collision_voices_dir, monkeypatch)
        vp.load_profiles()
        v1, p1, cp1 = _resolves_to_clone("bobs-burgers/bob", vp)
        v2, p2, cp2 = _resolves_to_clone("the-simpsons/bob", vp)
        assert p1 != "openai" and p2 != "openai"
        assert cp1.ref_audio != cp2.ref_audio


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
    # No default.wav — treated as a sample bin, not a voice, and skipped.
    return voices


class TestMouth4SampleBinDir:
    def test_sample_bin_dir_never_registers_as_a_voice(
        self, sample_bin_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(sample_bin_voices_dir, monkeypatch)
        profiles = vp.load_profiles()
        assert "mixtape" not in profiles

    def test_sample_bin_dir_skip_is_now_warning_visible(
        self, sample_bin_voices_dir, monkeypatch, caplog
    ):
        """Pre-fix this was DEBUG-only (invisible at INFO+). Post-fix it's a
        WARNING naming the cure — the skip is no longer invisible at any
        level an operator would normally run at."""
        vp = _reload_voice_profiles(sample_bin_voices_dir, monkeypatch)
        with caplog.at_level(logging.WARNING, logger="voicemode"):
            vp.load_profiles()
        assert any(
            "mixtape" in r.message and "default.wav" in r.message
            for r in caplog.records
        )

    def test_naming_a_sample_bin_dir_raises_before_any_endpoint_is_tried(
        self, sample_bin_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(sample_bin_voices_dir, monkeypatch)
        vp.load_profiles()
        exc = _never_reaches_wire("mixtape", vp)
        # "mixtape" registers as neither a voice (no default.wav / single
        # wav) nor a group (no subdirectories) — it's simply unresolvable,
        # and the error says so instead of quietly reaching Alloy.
        assert isinstance(exc, vp.Unresolvable)

    def test_naming_a_sample_bin_dir_names_the_specific_cure(
        self, sample_bin_voices_dir, monkeypatch
    ):
        """design.md §3.3: mouth 4 must be closed loudly at BOTH ends — the
        load-time WARNING already names the cure (previous test); the
        resolve-time error for directly naming the bin must too, not just a
        generic "unresolvable" with nearest-matches noise."""
        vp = _reload_voice_profiles(sample_bin_voices_dir, monkeypatch)
        vp.load_profiles()
        with pytest.raises(vp.Unresolvable) as exc_info:
            vp.resolve_voice("mixtape")
        message = str(exc_info.value)
        assert "sample bin" in message
        assert "default.wav" in message
        assert "take-1.wav" in message  # the specific ln -s hint


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
    """Distinct shape from the other four: pre-fix this did NOT reach Alloy
    — ``resolve_voice_expr`` caught the bad index and fell back to the SAME
    voice's default.wav (wrong clip, not wrong voice — design.md ruled it
    lower-severity and explicitly severable). fix-001 closes it anyway: the
    resolver core makes IndexOutOfRange free (no separate code path), so
    ``name[99]`` now raises, naming the actual sample count, instead of
    silently substituting the default clip."""

    def test_out_of_range_index_raises_naming_the_count(
        self, indexed_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(indexed_voices_dir, monkeypatch)
        vp.load_profiles()
        with pytest.raises(vp.IndexOutOfRange) as exc_info:
            vp.resolve_voice("samantha[99]")
        assert "2 sample" in str(exc_info.value)

    def test_out_of_range_index_raises_before_any_endpoint_is_tried(
        self, indexed_voices_dir, monkeypatch
    ):
        """Unlike mouths 1-4, this mouth never had a cross-provider blast
        radius — but now it doesn't even reach text_to_speech with the wrong
        clip; it fails at resolution, same as every other mouth."""
        vp = _reload_voice_profiles(indexed_voices_dir, monkeypatch)
        vp.load_profiles()
        exc = _never_reaches_wire("samantha[99]", vp)
        assert isinstance(exc, vp.IndexOutOfRange)

    def test_in_range_index_still_resolves_normally(self, indexed_voices_dir, monkeypatch):
        vp = _reload_voice_profiles(indexed_voices_dir, monkeypatch)
        vp.load_profiles()
        selected_voice, provider_type, clone_profile = _resolves_to_clone("samantha[0]", vp)
        assert provider_type != "openai"
        assert clone_profile.ref_audio.endswith(".wav")


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
    ``voice="aubrey-plaza:next-question"`` fell through to Alloy. Root
    cause: ``name:N``/``name:label`` (SuperDirt-style colon) is RESERVED by
    voices/README.md rule 7 ("leaves room for future colon-index access"),
    not implemented — design.md §3.2.3 keeps it reserved (no parser
    meaning). The bracket form ``name[N]`` IS implemented and works. Post-
    fix, the colon form is simply an opaque, unresolvable name: it now
    raises loudly instead of silently reaching Alloy."""

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

    def test_colon_form_raises_before_any_endpoint_is_tried(
        self, aubrey_plaza_voices_dir, monkeypatch
    ):
        vp = _reload_voice_profiles(aubrey_plaza_voices_dir, monkeypatch)
        vp.load_profiles()
        exc = _never_reaches_wire("aubrey-plaza:2", vp)
        assert isinstance(exc, vp.Unresolvable)
        # The nearest-matches hint should point back at the real voice.
        assert "aubrey-plaza" in str(exc)

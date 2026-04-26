"""Tests for voice profile loading and SuperDirt-style voice expressions."""

import importlib

import pytest


@pytest.fixture
def voices_dir(tmp_path, monkeypatch):
    """Build a voices/ tree with one voice (samantha) that has 3 samples."""
    voices = tmp_path / "voices"
    voices.mkdir()

    sam = voices / "samantha"
    sam.mkdir()
    (sam / "default.wav").write_bytes(b"riff-default")
    (sam / "default.txt").write_text("default transcript")
    (sam / "angry.wav").write_bytes(b"riff-angry")
    (sam / "angry.txt").write_text("angry transcript")
    (sam / "happy.wav").write_bytes(b"riff-happy")
    # No happy.txt — should fall back to default.txt
    (sam / "description.txt").write_text("Test voice")

    # Second voice with no transcript at all — exercises the warning path
    bare = voices / "bare"
    bare.mkdir()
    (bare / "default.wav").write_bytes(b"riff-bare")

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)
    return voices


@pytest.fixture
def vp(voices_dir):
    """Reload voice_profiles after env vars are set, return the module."""
    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)
    return voice_profiles


@pytest.fixture
def vp_remote(voices_dir, monkeypatch):
    """Same as vp but with VOICEMODE_REMOTE_VOICES_DIR set to /remote/voices."""
    monkeypatch.setenv("VOICEMODE_REMOTE_VOICES_DIR", "/remote/voices")
    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)
    return voice_profiles


# ---------- parse_voice_expr ----------

@pytest.mark.parametrize("expr,expected", [
    ("samantha", ("samantha", None)),
    ("samantha[0]", ("samantha", "[0]")),
    ("samantha[12]", ("samantha", "[12]")),
    ("samantha/angry.wav", ("samantha", "angry.wav")),
    ("/abs/path/file.wav", (None, "/abs/path/file.wav")),
    ("", (None, None)),
])
def test_parse_voice_expr(vp, expr, expected):
    assert vp.parse_voice_expr(expr) == expected


# ---------- profile loading ----------

def test_load_profiles_finds_voices_with_default_wav(vp):
    profiles = vp.load_profiles()
    assert set(profiles.keys()) == {"samantha", "bare"}


def test_profile_picks_up_description(vp):
    p = vp.get_profile("samantha")
    assert p.description == "Test voice"


def test_voice_with_no_transcript_loads_with_empty_ref_text(vp):
    p = vp.get_profile("bare")
    assert p is not None
    assert p.ref_text == ""


# ---------- bare name resolution ----------

def test_bare_name_resolves_to_default_wav(vp):
    p = vp.get_profile("samantha")
    assert p.ref_audio.endswith("/samantha/default.wav")
    assert p.ref_text == "default transcript"


# ---------- indexed selector ----------

def test_indexed_selector_picks_sorted_sample(vp):
    # Sorted: angry, default, happy
    assert vp.get_profile("samantha[0]").ref_audio.endswith("/angry.wav")
    assert vp.get_profile("samantha[1]").ref_audio.endswith("/default.wav")
    assert vp.get_profile("samantha[2]").ref_audio.endswith("/happy.wav")


def test_indexed_transcript_falls_back_to_default_txt(vp):
    # happy.wav has no happy.txt — should use default.txt
    p = vp.get_profile("samantha[2]")
    assert p.ref_text == "default transcript"


def test_indexed_with_matching_txt_uses_it(vp):
    # angry.wav has angry.txt
    p = vp.get_profile("samantha[0]")
    assert p.ref_text == "angry transcript"


def test_index_out_of_range_falls_back_to_default(vp):
    p = vp.get_profile("samantha[99]")
    assert p.ref_audio.endswith("/samantha/default.wav")


# ---------- relative path selector ----------

def test_relative_path_resolves_inside_voice_dir(vp):
    p = vp.get_profile("samantha/angry.wav")
    assert p.ref_audio.endswith("/samantha/angry.wav")
    assert p.ref_text == "angry transcript"


# ---------- absolute path escape hatch ----------

def test_absolute_path_passes_through(vp):
    p = vp.get_profile("/some/abs/path.wav")
    assert p.ref_audio == "/some/abs/path.wav"
    assert p.ref_text == ""
    # Should be marked as a clone voice so routing works
    assert vp.is_clone_voice("/some/abs/path.wav")


# ---------- is_clone_voice ----------

@pytest.mark.parametrize("expr", [
    "samantha", "samantha[0]", "samantha/angry.wav", "/abs/path.wav",
])
def test_is_clone_voice_recognises_all_expr_forms(vp, expr):
    assert vp.is_clone_voice(expr)


@pytest.mark.parametrize("expr", ["af_sky", "nova", "", "unknown"])
def test_is_clone_voice_rejects_non_clone(vp, expr):
    assert not vp.is_clone_voice(expr)


def test_get_profile_returns_none_for_unknown(vp):
    assert vp.get_profile("definitely-not-a-voice") is None


# ---------- remote path translation ----------

def test_remote_path_translation_rewrites_prefix(vp_remote):
    p = vp_remote.get_profile("samantha")
    assert p.ref_audio == "/remote/voices/samantha/default.wav"


def test_remote_path_translation_for_indexed(vp_remote):
    p = vp_remote.get_profile("samantha[0]")
    assert p.ref_audio == "/remote/voices/samantha/angry.wav"


def test_remote_path_translation_for_relative(vp_remote):
    p = vp_remote.get_profile("samantha/happy.wav")
    assert p.ref_audio == "/remote/voices/samantha/happy.wav"


def test_remote_path_translation_skips_absolute(vp_remote):
    p = vp_remote.get_profile("/literal/path.wav")
    assert p.ref_audio == "/literal/path.wav"


def test_no_remote_uses_local_absolute_path(vp, voices_dir):
    p = vp.get_profile("samantha")
    expected = str((voices_dir / "samantha" / "default.wav").resolve())
    assert p.ref_audio == expected

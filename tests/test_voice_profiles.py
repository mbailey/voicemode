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


# ---------- absolute path + sidecar transcript (VM-1278) ----------

def test_absolute_path_picks_up_sibling_sidecar(vp, tmp_path):
    """An existing clip with a <basename>.txt sidecar resolves ref_text."""
    clip = tmp_path / "louis-ck-bit.wav"
    clip.write_bytes(b"riff-clip")
    (tmp_path / "louis-ck-bit.txt").write_text("  so anyway, the thing is  \n")

    p = vp.get_profile(str(clip))
    assert p.ref_audio == str(clip)
    assert p.ref_text == "so anyway, the thing is"


def test_absolute_path_falls_back_to_default_txt(vp, tmp_path):
    """No matching-basename sidecar -> default.txt in the same dir is used."""
    clip = tmp_path / "take-3.wav"
    clip.write_bytes(b"riff-clip")
    (tmp_path / "default.txt").write_text("default clip transcript")

    p = vp.get_profile(str(clip))
    assert p.ref_text == "default clip transcript"


def test_absolute_path_no_sidecar_keeps_empty_ref_text(vp, tmp_path):
    """Existing clip but no sidecar at all -> ref_text stays empty."""
    clip = tmp_path / "orphan.wav"
    clip.write_bytes(b"riff-clip")

    p = vp.get_profile(str(clip))
    assert p.ref_audio == str(clip)
    assert p.ref_text == ""


def test_absolute_path_nonexistent_clip_keeps_empty_ref_text(vp):
    """Non-existent path (e.g. remote-only) -> ref_text empty, no crash."""
    p = vp.get_profile("/not/on/this/host/clip.wav")
    assert p.ref_audio == "/not/on/this/host/clip.wav"
    assert p.ref_text == ""


# ---------- relative / home path escape hatch (VM-1607) ----------

def test_parse_relative_path_is_made_absolute(vp):
    """./ and ../ exprs parse to (None, <absolute path>)."""
    name, sel = vp.parse_voice_expr("./clip.wav")
    assert name is None
    assert sel.startswith("/") and sel.endswith("/clip.wav")

    name, sel = vp.parse_voice_expr("../clip.wav")
    assert name is None
    assert sel.startswith("/") and sel.endswith("/clip.wav")


def test_relative_path_resolves_against_cwd(vp, tmp_path, monkeypatch):
    """`--voice ./clip.wav` resolves relative to the CWD, with sidecar."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ray.wav").write_bytes(b"riff-ray")
    (tmp_path / "ray.txt").write_text("  what are you doing here  \n")

    p = vp.get_profile("./ray.wav")
    assert p.ref_audio == str(tmp_path / "ray.wav")
    assert p.ref_text == "what are you doing here"
    assert vp.is_clone_voice("./ray.wav")


def test_parent_relative_path_resolves(vp, tmp_path, monkeypatch):
    """`../sub/clip.wav` walks up from the CWD."""
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "clip.wav").write_bytes(b"riff-clip")
    monkeypatch.chdir(sub)

    p = vp.get_profile("../clip.wav")
    assert p.ref_audio == str(tmp_path / "clip.wav")


def test_home_relative_path_expands(vp, tmp_path):
    """`~/clip.wav` expands against HOME.

    The conftest `isolate_home_directory` fixture maps ~ to
    ``tmp_path / "home"``, so the clip goes there.
    """
    fake_home = tmp_path / "home"
    (fake_home / "clip.wav").write_bytes(b"riff-clip")

    p = vp.get_profile("~/clip.wav")
    assert p.ref_audio == str(fake_home / "clip.wav")
    assert vp.is_clone_voice("~/clip.wav")


def test_relative_path_preserves_symlink_for_sidecar(vp, tmp_path, monkeypatch):
    """A symlinked default.wav keeps its own name (not the target's), so the
    default.txt sidecar is picked up — abspath must not resolve the symlink."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "take-7.wav").write_bytes(b"riff-real")
    (tmp_path / "default.txt").write_text("the default transcript")
    (tmp_path / "default.wav").symlink_to(tmp_path / "take-7.wav")

    p = vp.get_profile("./default.wav")
    # ref_audio is the symlink path, not the resolved target
    assert p.ref_audio == str(tmp_path / "default.wav")
    # and the sidecar resolves via the symlink's basename → default.txt
    assert p.ref_text == "the default transcript"


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


# ---------- recursive walk: grouped voice layouts (VL-26 impl-001) ----------

def _make_voice(parent, name, wav_bytes=b"riff", txt="transcript"):
    """Helper: drop a default.wav + default.txt voice dir under parent."""
    d = parent / name
    d.mkdir(parents=True)
    (d / "default.wav").write_bytes(wav_bytes)
    (d / "default.txt").write_text(txt)
    return d


@pytest.fixture
def grouped_voices_dir(tmp_path, monkeypatch):
    """Mixed-depth tree:

        voices/
          alan/default.wav                  (flat top-level)
          bobs-burgers/
            bob/default.wav                 (1-level group)
            linda/default.wav
          star-trek/
            tng/
              picard/default.wav            (3 levels deep)
    """
    voices = tmp_path / "voices"
    voices.mkdir()
    _make_voice(voices, "alan")
    _make_voice(voices, "bobs-burgers/bob")
    _make_voice(voices, "bobs-burgers/linda")
    _make_voice(voices, "star-trek/tng/picard")

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)
    return voices


@pytest.fixture
def vp_grouped(grouped_voices_dir):
    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)
    return voice_profiles


def test_grouped_voice_keyed_by_leaf_name(vp_grouped):
    profiles = vp_grouped.load_profiles()
    assert "bob" in profiles
    assert "linda" in profiles
    assert profiles["bob"].ref_audio.endswith("/bobs-burgers/bob/default.wav")


def test_three_deep_nested_voice_loads(vp_grouped, grouped_voices_dir):
    profiles = vp_grouped.load_profiles()
    assert "picard" in profiles
    assert profiles["picard"].ref_audio.endswith(
        "/star-trek/tng/picard/default.wav"
    )


def test_flat_and_nested_coexist(vp_grouped):
    profiles = vp_grouped.load_profiles()
    assert set(profiles.keys()) == {"alan", "bob", "linda", "picard"}


def test_voice_dir_field_records_resolved_path(vp_grouped, grouped_voices_dir):
    profiles = vp_grouped.load_profiles()
    assert profiles["alan"].voice_dir == str(grouped_voices_dir / "alan")
    assert profiles["bob"].voice_dir == str(
        grouped_voices_dir / "bobs-burgers" / "bob"
    )
    assert profiles["picard"].voice_dir == str(
        grouped_voices_dir / "star-trek" / "tng" / "picard"
    )


def test_indexed_selector_works_for_grouped_voice(tmp_path, monkeypatch):
    voices = tmp_path / "voices"
    voices.mkdir()
    bob_dir = voices / "bobs-burgers" / "bob"
    bob_dir.mkdir(parents=True)
    (bob_dir / "default.wav").write_bytes(b"d")
    (bob_dir / "default.txt").write_text("default")
    (bob_dir / "angry.wav").write_bytes(b"a")
    (bob_dir / "angry.txt").write_text("angry")

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    p = voice_profiles.get_profile("bob[0]")
    assert p.ref_audio.endswith("/bobs-burgers/bob/angry.wav")
    assert p.ref_text == "angry"


# ---------- collision detection ----------

def test_collision_drops_both_candidates(tmp_path, monkeypatch, caplog):
    voices = tmp_path / "voices"
    voices.mkdir()
    _make_voice(voices, "bobs-burgers/bob")
    _make_voice(voices, "the-simpsons/bob")
    _make_voice(voices, "alan")  # should still load

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib
    import logging

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    with caplog.at_level(logging.ERROR, logger="voicemode"):
        profiles = voice_profiles.load_profiles()

    assert "bob" not in profiles
    assert "alan" in profiles
    assert any(
        "collision" in rec.message.lower() and "bob" in rec.message
        for rec in caplog.records
    )


def test_collision_three_way_drops_all(tmp_path, monkeypatch, caplog):
    voices = tmp_path / "voices"
    voices.mkdir()
    _make_voice(voices, "show-a/bob")
    _make_voice(voices, "show-b/bob")
    _make_voice(voices, "show-c/bob")

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib
    import logging

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    with caplog.at_level(logging.ERROR, logger="voicemode"):
        profiles = voice_profiles.load_profiles()

    assert "bob" not in profiles
    error_records = [
        r for r in caplog.records
        if r.levelno >= logging.ERROR and "bob" in r.message
    ]
    assert len(error_records) == 1, (
        "Expected a single ERROR listing all three colliding paths"
    )
    msg = error_records[0].message
    assert "show-a/bob" in msg
    assert "show-b/bob" in msg
    assert "show-c/bob" in msg


# ---------- description suffix: (from <group>) (VL-26 impl-002) ----------


def test_top_level_voice_description_has_no_suffix(tmp_path, monkeypatch):
    voices = tmp_path / "voices"
    voices.mkdir()
    alan = _make_voice(voices, "alan")
    (alan / "description.txt").write_text("Australian rock voice.")

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    p = voice_profiles.get_profile("alan")
    assert p.description == "Australian rock voice."
    assert "(from" not in p.description


def test_grouped_voice_description_gets_suffix(tmp_path, monkeypatch):
    voices = tmp_path / "voices"
    voices.mkdir()
    bob = _make_voice(voices, "bobs-burgers/bob")
    (bob / "description.txt").write_text("Bob Belcher, burger flipper.")

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    p = voice_profiles.get_profile("bob")
    assert p.description == "Bob Belcher, burger flipper.\n(from bobs-burgers)"


def test_multi_level_grouped_voice_uses_joined_relative_path(
    tmp_path, monkeypatch
):
    voices = tmp_path / "voices"
    voices.mkdir()
    picard = _make_voice(voices, "star-trek/tng/picard")
    (picard / "description.txt").write_text("Make it so.")

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    p = voice_profiles.get_profile("picard")
    assert p.description == "Make it so.\n(from star-trek/tng)"


def test_grouped_voice_with_no_description_txt_still_gets_suffix(
    tmp_path, monkeypatch
):
    """A grouped voice without description.txt should get just the suffix
    (no leading newline, no empty body)."""
    voices = tmp_path / "voices"
    voices.mkdir()
    _make_voice(voices, "bobs-burgers/linda")  # no description.txt

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    p = voice_profiles.get_profile("linda")
    assert p.description == "(from bobs-burgers)"


# ---------- voice-with-subdir-ignored ----------

def test_subdirs_of_voice_dir_are_not_walked(tmp_path, monkeypatch):
    """A dir that qualifies as a voice short-circuits: its subdirs are not
    treated as candidate voices, even if they look like voice dirs."""
    voices = tmp_path / "voices"
    voices.mkdir()

    # Top-level voice with a 'samples/' subdir that itself contains
    # something that would otherwise look like a voice (default.wav).
    sam = voices / "samantha"
    sam.mkdir()
    (sam / "default.wav").write_bytes(b"d")
    (sam / "default.txt").write_text("default")

    samples = sam / "samples"
    samples.mkdir()
    (samples / "default.wav").write_bytes(b"d")  # tempting!
    (samples / "default.txt").write_text("inner")

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    profiles = voice_profiles.load_profiles()
    assert set(profiles.keys()) == {"samantha"}
    # 'samples' must NOT have been registered as its own voice
    assert "samples" not in profiles


# ---------- voice.md frontmatter transcript fallback (VM-1439) ----------

def _clone_add_voice_md(transcript: str) -> str:
    """Render a voice.md exactly like ``clone add`` does (json-encoded
    transcript scalar inside YAML frontmatter)."""
    import json

    return (
        "---\n"
        "name: lupe\n"
        "source: /tmp/clip.wav\n"
        "duration_seconds: 8.0\n"
        "format: mono 24kHz 16-bit PCM, loudnorm I=-16 TP=-1.5 LRA=11\n"
        f"transcript: {json.dumps(transcript, ensure_ascii=False)}\n"
        "---\n"
        "\n"
        "Auto-generated by voicemode clone add on 2026-06-20.\n"
    )


def test_voice_md_frontmatter_transcript_resolves_ref_text(tmp_path, monkeypatch):
    """A clone-add voice with default.wav + voice.md and NO default.txt — the
    exact broken layout — must load a non-empty ref_text from the voice.md
    ``transcript`` frontmatter field."""
    voices = tmp_path / "voices"
    voices.mkdir()
    lupe = voices / "lupe"
    lupe.mkdir()
    (lupe / "default.wav").write_bytes(b"riff-lupe")
    (lupe / "voice.md").write_text(_clone_add_voice_md("the quick brown fox jumped"))
    # No default.txt — this is exactly the broken clone-add layout.

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    p = voice_profiles.get_profile("lupe")
    assert p is not None
    assert p.ref_text == "the quick brown fox jumped"


def test_voice_md_frontmatter_decodes_escaped_characters(tmp_path, monkeypatch):
    """clone add writes the transcript as a json.dumps scalar, so escapes like
    quotes survive the YAML round-trip."""
    voices = tmp_path / "voices"
    voices.mkdir()
    lupe = voices / "lupe"
    lupe.mkdir()
    (lupe / "default.wav").write_bytes(b"riff-lupe")
    (lupe / "voice.md").write_text(_clone_add_voice_md('she said "hi" — then left'))

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    assert voice_profiles.get_profile("lupe").ref_text == 'she said "hi" — then left'


def test_txt_sidecar_wins_over_voice_md_frontmatter(tmp_path, monkeypatch):
    """When both a default.txt sidecar and a voice.md exist, the sidecar
    (primary lookup) wins — voice.md is only a fallback."""
    voices = tmp_path / "voices"
    voices.mkdir()
    lupe = voices / "lupe"
    lupe.mkdir()
    (lupe / "default.wav").write_bytes(b"riff-lupe")
    (lupe / "default.txt").write_text("sidecar transcript")
    (lupe / "voice.md").write_text(_clone_add_voice_md("frontmatter transcript"))

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    assert voice_profiles.get_profile("lupe").ref_text == "sidecar transcript"


def test_voice_md_without_transcript_field_loads_empty_ref_text(tmp_path, monkeypatch):
    """A voice.md missing the transcript field (or malformed) must not crash —
    ref_text falls back to empty and the loader warns."""
    voices = tmp_path / "voices"
    voices.mkdir()
    lupe = voices / "lupe"
    lupe.mkdir()
    (lupe / "default.wav").write_bytes(b"riff-lupe")
    (lupe / "voice.md").write_text("---\nname: lupe\n---\n\nNo transcript here.\n")

    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)

    import importlib

    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)

    p = voice_profiles.get_profile("lupe")
    assert p is not None
    assert p.ref_text == ""

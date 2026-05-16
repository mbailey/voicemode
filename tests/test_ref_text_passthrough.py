"""Tests for converse(ref_text=...) passthrough (VM-1278).

`resolve_ref_text` auto-detects whether the supplied value is a path to a
transcript file or literal transcript text:

- None        -> None  ("no override" sentinel)
- existing fp -> file contents, stripped
- anything    -> the literal string, unchanged
"""

from voice_mode.tools.converse import resolve_ref_text


def test_none_returns_none():
    assert resolve_ref_text(None) is None


def test_existing_file_path_is_read(tmp_path):
    f = tmp_path / "clip.txt"
    f.write_text("  the quick brown fox  \n")
    assert resolve_ref_text(str(f)) == "the quick brown fox"


def test_inline_text_passes_through_unchanged():
    text = "This is a literal transcript, not a path."
    assert resolve_ref_text(text) == text


def test_nonexistent_pathlike_string_treated_as_literal():
    # Looks like a path but doesn't exist -> used verbatim as the transcript.
    val = "/no/such/file/here.txt"
    assert resolve_ref_text(val) == val


def test_empty_string_is_preserved():
    # Empty string is a valid override (clone with no reference transcript);
    # it is NOT the None "no override" sentinel.
    assert resolve_ref_text("") == ""

"""Tests for turns schema discoverability (VM-1775 impl-006).

Slice 6 hands `turns` the literal per-argument schema description from
README ## Design, applied via `Annotated[..., Field(description=...)]` so it
actually lands in the MCP tool's JSON schema (FastMCP only auto-fills a
parameter's schema `description` from a docstring `Args:` block or an
explicit `Field`/`Annotated` annotation -- this project's `converse()`
docstring uses a hand-written "KEY PARAMETERS" prose section instead, which
FastMCP does not parse per-argument, so before this slice `turns` had no
schema-level description at all). This is deliberately scoped to `turns`
only; the broader per-argument migration for every other converse() param is
handed off to VM-1451, per the README's own note.

Covers:
  * The tool's JSON schema actually carries the description on `turns` (not
    just prose in the docstring humans read).
  * The description is the literal text from README ## Design, byte-for-byte
    -- this is the "golden" contract for the handoff, so a drift between the
    README and the shipped schema text is caught immediately.
  * The tool-description "KEY PARAMETERS" bullet for `turns` was updated to
    the say/ask line (README ## Design's "Tool-description bullet" text),
    not left describing the old speak-only-only P1 shape.
  * The killed-call recovery note (replies persist in conversation logs,
    even for a call that never returns) is documented somewhere reachable
    from the tool description.
"""

import re

import pytest

from voice_mode.server import mcp
from voice_mode.tools.converse import _TURNS_PARAM_DESCRIPTION, converse


def _collapse_whitespace(text: str) -> str:
    """Normalize the docstring's hand-wrapped lines to single spaces so
    substring checks aren't brittle against re-wrapping."""
    return re.sub(r"\s+", " ", text)


# Golden copy of README.md's "LITERAL SCHEMA-DESCRIPTION TEXT" for `turns`
# (## Design section). Kept as a literal duplicate here (same convention as
# the impl-003 golden tests for the survey JSON worked examples) so a change
# to either side shows up as a failing test, not a silent drift.
_README_LITERAL_TURNS_DESCRIPTION = (
    "Ordered list of utterances to deliver in ONE call, pipelined (turn N+1 is "
    "synthesized while turn N plays — no synth dead-air). Each turn is an "
    "object with EXACTLY ONE of: \"say\": str — speak this text and advance "
    "(no listening), or \"ask\": str — speak this text, then LISTEN and "
    "record the user's spoken reply. Optional per-turn overrides (each "
    "defaults to the call-level argument of the same name): \"voice\", "
    "\"speed\", \"tts_instructions\", \"pause_after_ms\"; and, meaningful on "
    "ask turns: \"listen_duration_max\", \"listen_duration_min\", "
    "\"vad_aggressiveness\". (\"wait_for_response\": true on a say turn is an "
    "accepted alias for \"ask\".) The call-level wait_for_response is IGNORED "
    "when turns is present — listening happens only for ask turns. If NO turn "
    "asks, the call speaks the sequence and returns a text summary. If ANY "
    "turn asks, the call returns a JSON object (as a string) with replies "
    "aligned to turns by index: {\"survey\": {\"completed\": bool, \"asked\": "
    "n, \"answered\": n, \"stopped_at\": null|{turn, phase, reason}, "
    "\"turns\": [{\"turn\": i, \"verb\": \"say\"|\"ask\", \"status\": "
    "\"spoken\"|\"answered\"|\"no_speech\"|\"tts_failed\"|\"stt_failed\"|"
    "\"not_reached\", \"reply\": str|null}, ...]}} — entries for no_speech / "
    "tts_failed / not_reached can simply be re-asked in a follow-up call. "
    "Keep surveys short (≤ ~7 ask turns) and give each ask turn a sensible "
    "\"listen_duration_max\" (30–45s for normal questions). Because turns "
    "advance automatically without reacting to each answer, make the survey "
    "legible to the user: OPEN with a leading say turn announcing how many "
    "questions there are (e.g. \"I've got 3 quick questions\") so they know a "
    "multi-turn survey is running, and at the TOP of your NEXT converse call "
    "acknowledge the answers you just collected — content-aware acknowledgment "
    "can't be pipelined mid-survey, so it belongs at the next call. During a "
    "survey "
    "the user can: answer early or finish answering with skip-forward, hear "
    "the question again with skip-back or by saying \"repeat\", pause with "
    "\"wait\", and abandon the survey with the stop control or by saying only "
    "\"break\" / \"stop the survey\" (returns the replies collected so far "
    "plus where it stopped). Unknown keys in a turn are rejected. \"play\" is "
    "reserved for a future phase. If both message and turns are given, turns "
    "wins."
)


def test_turns_param_description_constant_matches_readme_literal_text():
    """The module constant is the README's literal text, byte-for-byte."""
    assert _TURNS_PARAM_DESCRIPTION == _README_LITERAL_TURNS_DESCRIPTION


@pytest.mark.asyncio
async def test_turns_schema_property_carries_the_description():
    """The MCP tool's JSON schema for `turns` exposes the description --
    i.e. it's reachable via Annotated/Field, not just docstring prose."""
    tool = await mcp.get_tool("converse")
    turns_schema = tool.parameters["properties"]["turns"]
    assert turns_schema["description"] == _TURNS_PARAM_DESCRIPTION


@pytest.mark.asyncio
async def test_turns_schema_description_covers_key_contract_points():
    """Spot-check the substance survives (verbs, controls, return shape) --
    guards against a future edit accidentally truncating the text."""
    tool = await mcp.get_tool("converse")
    desc = tool.parameters["properties"]["turns"]["description"]
    for expected in (
        '"say": str',
        '"ask": str',
        "listen_duration_max",
        "vad_aggressiveness",
        "wait_for_response",
        "skip-forward",
        "skip-back",
        '"break"',
        '"stopped_at"',
        "turns wins",
    ):
        assert expected in desc, f"missing {expected!r} from turns schema description"


def test_tool_description_turns_bullet_uses_say_ask_line():
    """The docstring's KEY PARAMETERS `turns` bullet was updated off the old
    P1 speak-only-only wording onto the say/ask line -- not left stale."""
    doc = _collapse_whitespace(converse.__doc__)
    assert '{"say": ...} speaks' in doc
    assert '{"ask": ...} speaks then listens and collects the reply' in doc
    # The old P1-only wording ("Speak-only (no reply collection in this
    # version)") must be gone -- that claim is no longer true.
    assert "Speak-only (no reply collection in this version)" not in doc


def test_tool_description_documents_killed_call_recovery():
    """The docstring documents that already-collected replies survive a
    killed/crashed call (Decision 7 crash persistence), not just the happy
    path's JSON return."""
    doc = converse.__doc__
    assert "conversation logs" in doc
    assert "killed" in doc.lower() or "crash" in doc.lower()


def test_tool_description_mentions_break_and_skip_controls_for_turns():
    """The turns bullet at least names the survey controls (full detail
    lives in the schema description itself, referenced from the bullet)."""
    doc = converse.__doc__
    turns_bullet_start = doc.index("• turns (list, optional)")
    next_bullet = doc.index("\n• ", turns_bullet_start + 1)
    turns_bullet = doc[turns_bullet_start:next_bullet]
    assert "skip-forward" in turns_bullet
    assert "skip-back" in turns_bullet or "repeat" in turns_bullet
    assert "break" in turns_bullet

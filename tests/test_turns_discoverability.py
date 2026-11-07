"""Tests for turns schema discoverability (VM-1775 impl-006; re-expressed VM-2099).

Slice 6 hands `turns` a per-argument schema description, applied via
`Annotated[..., Field(description=...)]` so it actually lands in the MCP tool's
JSON schema (FastMCP only auto-fills a parameter's schema `description` from a
docstring `Args:` block or an explicit `Field`/`Annotated` annotation -- this
project's `converse()` docstring uses a hand-written "KEY PARAMETERS" prose
section instead, which FastMCP does not parse per-argument, so before that slice
`turns` had no schema-level description at all).

WHY THIS FILE NO LONGER PINS THE TEXT BYTE-FOR-BYTE (VM-2099)
-------------------------------------------------------------
It used to hold `_README_LITERAL_TURNS_DESCRIPTION`: a copy of VM-1775's task
README ## Design text, asserted equal to the shipped constant. The sync intent
was legitimate -- "the shipped schema text is exactly what the design specified"
-- but it was expressed as an ETERNAL CONTENT PIN, and the content it pinned
included advice: "give each ask turn a sensible listen_duration_max (30-45s for
normal questions)". That advice was the bug in VM-2099 (agents absorbed the
number and cut the user off mid-answer), and the pin meant DELETING the bug
turned CI red. The suite had become the defect's defence.

The principle, so the next author does not rebuild the trap: **a sync test may
assert two copies match only when one side is mechanically DERIVED from the
single source at test time. A third copy embedded in the test is not a sync --
it is an embalming.** The "source" here was a completed task's README, outside
this repo and frozen; no derivation was possible, so the byte-equality assertion
could only ever pin history.

What replaces it, keeping every intent that was real:
  * the wiring is still asserted (the schema property carries the description --
    that comparison is DERIVED, both sides read from the module at test time, so
    it stays honest as the text is edited);
  * the substance is asserted STRUCTURALLY (the description exists, is
    non-trivial, and names the turn vocabulary, the per-turn override keys, the
    controls and the survey return shape) -- an accidental truncation still
    fails, and rewording deliberately does not;
  * the NEGATIVE property that actually matters -- no numeric listening-ceiling
    advice in this or any other teaching position -- is asserted by
    `tests/test_no_cap_teaching.py`, by pattern, across the whole doc/prompt/
    schema space. Advice content is therefore checked for the property it must
    have, not frozen at a wording.

Covers:
  * The tool's JSON schema actually carries the description on `turns` (not
    just prose in the docstring humans read).
  * The description still documents the turn vocabulary, per-turn overrides,
    survey controls and return shape (structural, not byte-for-byte).
  * The say/ask verbs, the survey controls and the killed-call recovery note
    (replies persist in the conversation log, even for a call that never
    returns) are documented on the surface the agent reads.

VM-2442 (the context diet) moved every parameter's prose out of the docstring
and into the schema: the docstring no longer has a "KEY PARAMETERS" section, so
the checks below read `_TURNS_PARAM_DESCRIPTION`, which IS the schema text
(the derived-equality test above proves it), not `converse.__doc__`.
"""

import re

import pytest

from voice_mode.server import mcp
from voice_mode.tools.converse import _TURNS_PARAM_DESCRIPTION, converse


def _collapse_whitespace(text: str) -> str:
    """Normalize the docstring's hand-wrapped lines to single spaces so
    substring checks aren't brittle against re-wrapping."""
    return re.sub(r"\s+", " ", text)


# The per-turn override keys and survey vocabulary the description must keep
# documenting. These are STRUCTURAL facts about the turns feature (they name
# things a caller has to be able to find), not a copy of the advice prose --
# renaming or dropping one is a real contract change; rewording a sentence is
# not. Deliberately no durations here: numbers in a teaching position are what
# VM-2099 removed, and tests/test_no_cap_teaching.py fails if one comes back.
_REQUIRED_VOCABULARY = (
    '"say": str',
    '"ask": str',
    "listen_duration_max",
    "listen_duration_min",
    "vad_aggressiveness",
    '"ack"',
    "pause_after_ms",
    "wait_for_response",
    "skip-forward",
    "skip-back",
    '"break"',
    '"survey"',
    '"stopped_at"',
    "turns wins",
)


def test_turns_param_description_is_substantive():
    """The description exists and is real prose, not an empty string or a stub
    left behind by an edit. (What it MUST NOT contain -- a numeric listening
    ceiling -- is asserted by tests/test_no_cap_teaching.py, which scans this
    constant along with every other teaching position.)"""
    assert _TURNS_PARAM_DESCRIPTION.strip(), "turns lost its schema description"
    assert len(_collapse_whitespace(_TURNS_PARAM_DESCRIPTION)) > 800, (
        "the turns description has been truncated -- it documents the whole "
        "say/ask vocabulary, the survey controls and the return shape"
    )


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
    for expected in _REQUIRED_VOCABULARY:
        assert expected in desc, f"missing {expected!r} from turns schema description"


def test_turns_description_uses_the_say_ask_verbs():
    """Both verbs are documented where the agent reads them (the schema), and
    the old P1 speak-only claim ("no reply collection in this version"), which
    is no longer true, is gone from the tool entirely."""
    desc = _collapse_whitespace(_TURNS_PARAM_DESCRIPTION)
    assert '"say": str' in desc and '"ask": str' in desc
    assert "Speak-only (no reply collection in this version)" not in desc
    assert "Speak-only (no reply collection in this version)" not in converse.__doc__


def test_turns_description_documents_killed_call_recovery():
    """Already-collected replies survive a killed/crashed call (Decision 7
    crash persistence); the agent is told so on the schema, not just shown the
    happy path's JSON return."""
    desc = _TURNS_PARAM_DESCRIPTION.lower()
    assert "conversation log" in desc
    assert "killed" in desc or "crash" in desc


def test_turns_description_names_break_and_skip_controls():
    """The survey controls a user can exercise mid-run are named on the
    schema text, so an agent can tell the user about them."""
    desc = _TURNS_PARAM_DESCRIPTION
    assert "skip-forward" in desc
    assert "skip-back" in desc or "repeat" in desc
    assert "break" in desc


def test_tool_docstring_does_not_restate_the_parameters():
    """VM-2442: one description per parameter, in the schema. The docstring
    carries the contract in prose and points at the resources; it does not
    grow a second, hand-maintained parameter list again."""
    doc = converse.__doc__
    assert "KEY PARAMETERS" not in doc
    assert "• " not in doc, "a bulleted parameter list is back in the docstring"
    assert len(doc.split()) < 200, "the tool description has outgrown its brief (VM-2442)"

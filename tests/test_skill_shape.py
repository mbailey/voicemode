"""VM-2442 — the agent-facing text stays on its diet.

Mike's brief (voice, 2026-10-04): the tool description is the shipwreck kit and
must work alone; the skill supplements it and never duplicates it; the SKILL.md
body stays under 500 tokens; references are flat, one level down, each with
front matter and a short lead; the transcript echo is gone from both surfaces.

Words stand in for tokens here, because the test deps carry no tokenizer: 500
tokens of English Markdown is about 380 words on o200k_base (measured on this
skill), so the ceiling below leaves a little room. If this fires, cut, or move
the text to a reference; do not raise the number without the brief changing.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / ".claude" / "skills"
SKILL = SKILLS / "voicemode" / "SKILL.md"
REFS = SKILLS / "voicemode" / "references"
CONVERSE = REPO / "voice_mode" / "tools" / "converse.py"

MAX_BODY_WORDS = 400
MAX_LEAD_WORDS = 25
ECHO_MARKERS = ("ASSISTANT (voicemode)", "USER (voicemode)", "<echo>")


def _split_front_matter(text: str) -> tuple[str, str]:
    assert text.startswith("---\n"), "front matter is required"
    end = text.index("\n---", 4)
    return text[4:end], text[end + 4:].lstrip("\n")


def test_there_is_one_voicemode_skill():
    """converse, impressions, voicemode-dj and voicemode-connect were folded
    into this one (VM-2442); a second skill is a second place to drift."""
    assert sorted(p.name for p in SKILLS.iterdir() if p.is_dir()) == ["voicemode"]


def test_skill_body_stays_under_the_budget():
    fm, body = _split_front_matter(SKILL.read_text(encoding="utf-8"))
    assert re.search(r"^name: voicemode$", fm, re.M)
    assert re.search(r"^description: .{40,}", fm, re.M)
    words = len(body.split())
    assert words <= MAX_BODY_WORDS, (
        f"SKILL.md body is {words} words; the budget is {MAX_BODY_WORDS} "
        "(~500 tokens). Move detail into a reference instead."
    )


def test_references_are_flat_with_front_matter_and_a_lead():
    files = sorted(REFS.iterdir())
    assert files, "the skill needs its references"
    for p in files:
        assert p.is_file() and p.suffix == ".md", f"{p}: references are flat .md files, one level"
        fm, body = _split_front_matter(p.read_text(encoding="utf-8"))
        assert re.search(r"^name: " + re.escape(p.stem) + r"$", fm, re.M), f"{p}: name must match the file"
        assert re.search(r"^description: .{20,}", fm, re.M), f"{p}: description missing"
        lead = body.strip().split("\n\n", 1)[0]
        assert not lead.startswith("#"), f"{p}: the lead comes before the heading"
        assert len(lead.split()) <= MAX_LEAD_WORDS, f"{p}: lead is {len(lead.split())} words"
    assert (REFS / "linger.md").exists(), "linger is the first concept page (the brief)"


REF_DEFINITION = re.compile(r"^\[([^\]]+)\]:\s*(\S+)$", re.M)
REF_USE = re.compile(r"(?<!\\)\[([^\]\n]+)\](?![\(\[:])")


def test_skill_links_resolve_one_level_down():
    """Mike's review (2026-10-04): the body points at a reference with a
    shortcut reference link, `[linger]`, whose text IS the file's name, so a
    reader of the top alone knows where it lives; the `## References` list at
    the foot defines each name once so the links render (on GitHub too)."""
    text = SKILL.read_text(encoding="utf-8")
    definitions = REF_DEFINITION.findall(text)
    assert definitions, "the References list at the foot defines the links"
    defined = dict(definitions)
    assert len(defined) == len(definitions), "a name used twice gets ONE definition"
    for name, link in defined.items():
        target = (SKILL.parent / link).resolve()
        assert target.is_file(), f"[{name}]: dangling link {link}"
        assert target.parent == REFS, f"[{name}]: references live one level down, in references/"
        assert target.stem == name, f"[{name}] must be named for its file, {target.name}"

    body = REF_DEFINITION.sub("", text)
    body = re.sub(r"`[^`\n]*`", "", body)  # a [bracket] inside code is not a link
    used = set(REF_USE.findall(body))
    assert used, "the body points at its references"
    assert used <= set(defined), f"used without a definition: {sorted(used - set(defined))}"
    assert set(defined) <= used, f"defined but never used: {sorted(set(defined) - used)}"
    assert not re.search(r"\]\(references/", text), "inline links are gone; write [name] and define it at the foot"


def test_the_echo_rule_is_gone_from_both_surfaces():
    """Mike, 2026-10-04: the ASSISTANT/USER (voicemode) echo doubled everything
    and the Talk app already shows the conversation. It lived in the skill and
    in the converse tool description; both are checked."""
    for p in SKILLS.rglob("*.md"):
        text = p.read_text(encoding="utf-8")
        for marker in ECHO_MARKERS:
            assert marker not in text, f"{p} still carries the echo rule ({marker!r})"
    tree = ast.parse(CONVERSE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for marker in ECHO_MARKERS:
                assert marker not in node.value, f"converse.py:{node.lineno} still carries the echo rule"

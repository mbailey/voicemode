"""VM-2099 — the parameter reference has ONE source; copies may not reappear.

WHY THIS EXISTS (read before editing, especially before adding a second copy).

`converse()`'s parameters were documented twice: `voice_mode/resources/docs/
parameters.md` (served to agents as `voicemode://docs/parameters`) and
`docs/reference/converse-parameters.md` (the documentation site). Nothing kept
them in step, so they drifted — by July 2026 each carried whole sections the
other had never heard of, and both carried a hardcoded listening ceiling long
after the project decided the ceiling belongs to the user's config.

That drift is the *mechanism* behind VM-2099, not a tidiness complaint: a fix
applied to one copy leaves the other teaching the old thing, and the next author
edits whichever copy they happened to open. VM-746 fixed the advice in Feb 2026
and it was back by July, in a surface its author never saw.

The collapse: `voice_mode/resources/docs/parameters.md` is the single source (it
ships inside the package, so it is the copy that must be right), and the site
page *includes* it with a pymdownx snippet rather than restating it. The site
path is kept — docs and skills link to it — but it holds no content of its own.

This file makes the collapse durable. Re-splitting the reference now requires
deleting a test that explains why it exists, which is the point: last time,
divergence required no deliberate act at all.

WHAT COUNTS AS A DUPLICATE

A file that is *shaped like* a parameter reference. Two shapes, because the
reference was copied in two different sizes:

  * the full form — several distinct converse parameter names alongside several
    `**Type:**` field markers;
  * the summary table — a `| Parameter | Default | ... |` table listing several
    converse parameters. A five-row teaser is still a second place where a
    default is written down by hand, and it goes stale the same way: the plugin
    guide's table carried a hardcoded listening ceiling long after the project
    decided the user's config owned it.

Detected by pattern over the whole tree, not by a list of today's files — the
copy that hurts us next will be one nobody has created yet. A page that merely
mentions parameters in prose, or that includes the source, does not trip it.

The scanned space, stated: every `.md/.markdown/.mdx/.rst/.txt` file under the
repo root, tracked or not, minus build/vendor directories, dated records
(`CHANGELOG*`, `docs/.archive/`) and `tests/`. Two boundaries this check does not
close: a table that states defaults without labelling the column `Default` (the
anchor that distinguishes a defaults copy from `parameter-naming-proposals.md`'s
rename table), and a copy that describes parameters in freeform prose with
neither field markers nor a table. For the listening ceiling specifically —
the value this all exists to protect — `test_no_cap_teaching.py` scans the same
tree by number-near-token and covers both.

IF THIS FIRES ON YOU, the fix is to include or link the single source, not to
add an exemption. If your document genuinely needs different content, ask what
happens to it the day the source changes and nobody remembers you exist.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, List

REPO_ROOT = Path(__file__).resolve().parent.parent

# The single source of truth, and the site page that must include it.
SOURCE_REL = "voice_mode/resources/docs/parameters.md"
SITE_PAGE_REL = "docs/reference/converse-parameters.md"

SOURCE = REPO_ROOT / SOURCE_REL
SITE_PAGE = REPO_ROOT / SITE_PAGE_REL

# pymdownx.snippets include, with `base_path` = repo root (see mkdocs.yml).
_SNIPPET_INCLUDE = re.compile(r'^\s*(?:-{2,})8<-{2,}\s*"([^"]+)"\s*$', re.MULTILINE)

# The shape of a parameter reference: field markers plus distinctive converse
# parameter names. Generic names (`voice`, `speed`, `transport`) are deliberately
# absent -- they appear in ordinary prose.
_TYPE_MARKER = re.compile(r"^\*\*Type:\*\*", re.MULTILINE)
_PARAM_NAMES = (
    "wait_for_response",
    "listen_duration_max",
    "listen_duration_min",
    "tts_provider",
    "tts_model",
    "tts_instructions",
    "disable_silence_detection",
    "vad_aggressiveness",
    "chime_leading_silence",
    "chime_trailing_silence",
    "audio_format",
    "chime_enabled",
    "skip_tts",
    "room_name",
    "time_in_response",
)
_MIN_TYPE_MARKERS = 3
_MIN_DISTINCT_PARAMS = 4

# The summary shape: a markdown table that states parameter DEFAULTS. Anchored on
# a "default" column header, which is what makes it a copy of the reference rather
# than a table that happens to mention parameters -- `parameter-naming-proposals.md`
# tabulates rename candidates (`| Current | Proposed | Reason |`) and states no
# default, so it is not a second place a default can go stale.
_TABLE_ROW = re.compile(r"^\s*\|(.*)\|\s*$", re.MULTILINE)
_TABLE_SEPARATOR = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
_MIN_DISTINCT_TABLE_PARAMS = 3

_DOC_SUFFIXES = frozenset({".md", ".markdown", ".mdx", ".rst", ".txt"})
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "build",
        "dist",
        "htmlcov",
        "site",
        ".idea",
        ".vscode",
    }
)


def _is_exempt(rel_path: Path) -> bool:
    """Path-level exemptions -- each a reason, not a location."""
    parts = rel_path.parts
    name = rel_path.name

    if rel_path.as_posix() == SOURCE_REL:  # the source is allowed to be itself
        return True
    if name.upper().startswith("CHANGELOG"):  # dated record
        return True
    if ".archive" in parts or "archive" in parts:  # dated record
        return True
    if parts and parts[0] == "tests":  # fixtures, incl. this file's own strings
        return True
    return False


def _iter_docs(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix.lower() not in _DOC_SUFFIXES:
            continue
        if _is_exempt(rel):
            continue
        yield path


def _looks_like_a_parameter_reference(text: str) -> bool:
    """The full form: field markers plus several distinct parameter names."""
    if len(_TYPE_MARKER.findall(text)) < _MIN_TYPE_MARKERS:
        return False
    distinct = {name for name in _PARAM_NAMES if name in text}
    return len(distinct) >= _MIN_DISTINCT_PARAMS


def _looks_like_a_parameter_table(text: str) -> bool:
    """The summary form: a markdown table with a `Default` column whose rows are
    converse parameters. Only the FIRST cell of a row counts, so a table that
    merely mentions a parameter in a description does not trip."""
    named: set = set()
    in_defaults_table = False
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            in_defaults_table = False
            continue
        if _TABLE_SEPARATOR.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not in_defaults_table:
            # A header row is one that names a default column.
            if any(c.lower().startswith("default") for c in cells):
                in_defaults_table = True
            continue
        first = cells[0] if cells else ""
        named |= {name for name in _PARAM_NAMES if name in first}
    return len(named) >= _MIN_DISTINCT_TABLE_PARAMS


def _is_a_copy_of_the_reference(text: str) -> bool:
    return _looks_like_a_parameter_reference(text) or _looks_like_a_parameter_table(text)


def find_duplicate_parameter_references(root: Path) -> List[str]:
    """Every file outside the single source that restates the parameter reference."""
    return [
        str(path.relative_to(root))
        for path in _iter_docs(root)
        if _is_a_copy_of_the_reference(path.read_text(encoding="utf-8", errors="replace"))
    ]


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def test_the_single_source_is_the_parameter_reference():
    """The source exists and actually holds the reference -- so the checks below
    cannot pass by everything being empty."""
    assert SOURCE.is_file(), f"{SOURCE_REL} is the single source and must exist"
    text = SOURCE.read_text(encoding="utf-8")
    assert _looks_like_a_parameter_reference(text), (
        f"{SOURCE_REL} no longer looks like the parameter reference. If the "
        "reference moved, move this test's SOURCE_REL with it -- and update the "
        f"include in {SITE_PAGE_REL} in the same change."
    )


def test_the_site_page_includes_the_source_instead_of_copying_it():
    """The site page keeps its URL (docs and skills link to it) but holds no
    content of its own: it includes the source."""
    assert SITE_PAGE.is_file(), (
        f"{SITE_PAGE_REL} must keep existing -- SKILL.md and docs/reference/"
        "environment.md link to it. Include the source here; do not delete the path."
    )
    text = SITE_PAGE.read_text(encoding="utf-8")

    includes = _SNIPPET_INCLUDE.findall(text)
    assert SOURCE_REL in includes, (
        f"{SITE_PAGE_REL} must include the single source with a snippet:\n"
        f'    --8<-- "{SOURCE_REL}"\n'
        f"found includes: {includes or 'none'}"
    )
    for target in includes:
        assert (REPO_ROOT / target).is_file(), (
            f"{SITE_PAGE_REL} includes '{target}', which does not exist. A "
            "pymdownx snippet with a missing target renders as nothing -- the "
            "page would go silently blank."
        )

    assert not _looks_like_a_parameter_reference(text), (
        f"{SITE_PAGE_REL} has grown a hand-maintained parameter reference again. "
        "That is exactly how the two copies drifted apart before VM-2099: edit "
        f"{SOURCE_REL} and let the include carry it here."
    )


def test_the_served_resource_is_the_single_source():
    """`voicemode://docs/parameters` serves the source file itself -- agents and
    the documentation site read the same bytes."""
    from voice_mode.resources import docs_resources

    served = docs_resources.parameters
    served = getattr(served, "fn", served)  # unwrap the FastMCP resource
    assert served() == SOURCE.read_text(encoding="utf-8")


def test_no_second_hand_maintained_parameter_reference_in_the_repo():
    duplicates = find_duplicate_parameter_references(REPO_ROOT)
    assert not duplicates, (
        "A second copy of the converse parameter reference has appeared. Two "
        "hand-maintained copies drift -- that drift is how stale listening-ceiling "
        f"advice outlived its fix (VM-2099). Include or link {SOURCE_REL} instead. "
        "Copies found:\n  " + "\n  ".join(duplicates)
    )


# ---------------------------------------------------------------------------
# Proving the checks can fail (the inversion IS the acceptance).
# ---------------------------------------------------------------------------


def _write(root: Path, rel: str, body: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


_A_HAND_COPY = (
    "# Parameters\n\n"
    "### wait_for_response\n**Type:** boolean\nListen after speaking.\n\n"
    "### listen_duration_max\n**Type:** number\nCeiling on one listening turn.\n\n"
    "### tts_provider\n**Type:** string\nProvider selection.\n\n"
    "### skip_tts\n**Type:** boolean\nText only.\n"
)


def test_detector_catches_a_brand_new_copy(tmp_path):
    """The recurrence vector: a copy in a file that does not exist yet. A
    whitelist of July 2026's two files fails this test by construction."""
    _write(tmp_path, "docs/guides/some-guide-written-later/parameters.md", _A_HAND_COPY)
    assert find_duplicate_parameter_references(tmp_path) == [
        "docs/guides/some-guide-written-later/parameters.md"
    ]


def test_detector_catches_the_site_page_regrowing_a_copy(tmp_path):
    """The literal regression this slice closed: the site page restated the
    reference instead of including it."""
    _write(tmp_path, SITE_PAGE_REL, _A_HAND_COPY)
    assert find_duplicate_parameter_references(tmp_path) == [SITE_PAGE_REL]


def test_detector_allows_an_include_only_stub(tmp_path):
    """The cure must be expressible."""
    _write(tmp_path, SITE_PAGE_REL, f'--8<-- "{SOURCE_REL}"\n')
    assert find_duplicate_parameter_references(tmp_path) == []


_A_DEFAULTS_TABLE = (
    "## Converse Tool Parameters\n\n"
    "| Parameter | Default | Description |\n"
    "|-----------|---------|-------------|\n"
    "| `message` | (required) | Text to speak |\n"
    "| `wait_for_response` | true | Listen after speaking |\n"
    "| `listen_duration_max` | 120 | Ceiling on recording time |\n"
    "| `vad_aggressiveness` | 3 | Voice detection strictness |\n"
)


def test_detector_catches_a_summary_defaults_table(tmp_path):
    """The shape the plugin guide had: five rows, hand-maintained, and one of them
    a hardcoded listening ceiling that outlived the decision to let config own it."""
    _write(tmp_path, "docs/guides/some-plugin.md", _A_DEFAULTS_TABLE)
    assert find_duplicate_parameter_references(tmp_path) == ["docs/guides/some-plugin.md"]


def test_detector_allows_a_table_that_states_no_defaults(tmp_path):
    """`parameter-naming-proposals.md`'s real shape: a rename discussion. It
    tabulates parameters but no default, so nothing in it can go stale against the
    source."""
    _write(
        tmp_path,
        "voice_mode/resources/docs/parameter-naming-proposals.md",
        "| Current | Proposed | Reason |\n|---|---|---|\n"
        "| `skip_tts` | `text_only_mode` | Positive framing |\n"
        "| `listen_duration_max` | `listen_timeout_seconds` | More explicit |\n"
        "| `vad_aggressiveness` | `silence_detection_sensitivity` | Avoid jargon |\n",
    )
    assert find_duplicate_parameter_references(tmp_path) == []


def test_detector_allows_a_table_that_only_mentions_a_parameter_in_prose(tmp_path):
    """Only the first cell of a row counts: a description mentioning parameters is
    not a copy of the reference."""
    _write(
        tmp_path,
        "docs/guides/a-guide.md",
        "| Setting | Default | Notes |\n|---|---|---|\n"
        "| `VOICEMODE_DEFAULT_LISTEN_DURATION` | see docs | owns `listen_duration_max` |\n"
        "| `VOICEMODE_SKIP_TTS` | false | backs `skip_tts` |\n"
        "| `VOICEMODE_VAD` | on | backs `vad_aggressiveness` |\n",
    )
    assert find_duplicate_parameter_references(tmp_path) == []


def test_detector_allows_prose_that_merely_mentions_parameters(tmp_path):
    """A guide is not a reference: no `**Type:**` field markers, no trip."""
    _write(
        tmp_path,
        "docs/guides/a-guide.md",
        "Call `converse()` with `wait_for_response`, `skip_tts`, `tts_provider` "
        "and `vad_aggressiveness` as needed; the full reference lives in the "
        "voicemode-parameters resource.\n",
    )
    assert find_duplicate_parameter_references(tmp_path) == []


def test_detector_ignores_dated_records(tmp_path):
    """History is evidence of what the docs used to say, not a live copy."""
    _write(tmp_path, "CHANGELOG.md", _A_HAND_COPY)
    _write(tmp_path, "docs/.archive/old-parameters.md", _A_HAND_COPY)
    assert find_duplicate_parameter_references(tmp_path) == []

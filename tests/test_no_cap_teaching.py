"""VM-2099 — the teaching-position check: nothing may teach a listening CEILING.

WHY THIS EXISTS (read before editing, especially before adding an exemption).

Mike could not predict when voicemode would cut him off mid-answer, because
every agent invented its own `listen_duration_max` — absorbed ambiently from
documentation and examples rather than chosen by anyone. The ceiling belongs to
the user's config (`VOICEMODE_DEFAULT_LISTEN_DURATION`); a value an agent passes
replaces it silently. VM-746 (Feb 2026) already fixed this once with guidance
prose, and it decayed in five months: the recurrence vector was NOT the old text
rotting, it was a NEW feature's docs (VM-1775's `turns` schema advice, "give each
ask turn a sensible listen_duration_max (30–45s for normal questions)") written
by an author who had no reason to ever see VM-746's section — and then pinned
byte-for-byte by a test, so CI defended the defect.

Doc edits fix today. Only a check meets the next feature's author. That is this
file's whole job, and it is why it is written as a PATTERN SCAN over the whole
doc/prompt/schema space rather than a list of the surfaces that were wrong in
July 2026: **a whitelist of today's locations cannot fail on a file that does not
exist yet, which is exactly the file that broke this last time.**

WHAT COUNTS AS A VIOLATION

A ceiling number sitting in a teaching position — doc prose, an example call, a
parameter description, a tool docstring, a prompt. Concretely, two rules:

  R1 (proximity)   a numeral within ``_NEAR_RADIUS`` characters of a ceiling
                   token. Catches `listen_duration_max=300`, `(number, default:
                   120)`, `| listen_duration_max | 120 |`, `"listen_duration_max"
                   (30–45s for normal questions)`, and the shape a future author
                   will invent that nobody has thought of yet: a bare number
                   next to the name.
  R2 (unit)        a duration-with-unit number (`120s`, `45 seconds`, `2 min`)
                   anywhere in a block or markdown section that names a ceiling
                   token — catches advice a couple of lines below the name, e.g.
                   "Response will be exceptionally long (>120s)".

Digits are the signal, NOT the dash. The advice that caused VM-2099 used an
EN-DASH (U+2013), so `grep "30-45s"` returned clean — a false negative that hid
the defect; on the wire the same text is JSON-escaped to `30\\u201345s`, which
false-cleans an en-dash-aware grep too. This check reads all three the same way:
`\\uXXXX` escapes are decoded before scanning (``_decode_json_escapes``) and the
match is on numerals, so no dash form can slip past.

The CURE the corrected surfaces model, and the one this check leaves available:
name the CONFIG KEY, never a number ("default: the user's
VOICEMODE_DEFAULT_LISTEN_DURATION"). A config key has no digits, so honest
documentation of the default is always expressible; only *choosing a number for
the user* is not.

EXEMPTIONS — each is a reason, not a location

  * The FLOOR (`listen_duration_min`, `min_listen_duration`, "minimum listen
    duration") is not scanned at all. It is a different direction and the
    legitimate adjacent case (VM-1168): a floor protects thinking pauses and
    CANNOT cut an answer short, so numbers for it may be discussed. Encoded in
    ``_CEILING_TOKEN`` itself.
  * Dated records — `CHANGELOG*` (and the `changelog://` resource generated from
    it) and `docs/.archive/`. A historical statement ("changed the default from
    45s to 120s") is evidence of what happened, not advice about what to do.
  * The config's own home — `*.env` / `*.env.example` / anything named
    `voicemode.env*`. That IS where the number belongs; a config file stating a
    value is the fix working, not the defect.
  * `tests/` — including this file. Test numbers are arguments under test, i.e.
    usage rather than advice, and no agent reads them. Note the loophole this
    does NOT open: a test that *pins* advice (the VM-1775 mechanism) must contain
    a copy of a live string, and the live source copy is scanned — so pinning
    cannot hide a violation, it can only duplicate one.
  * Python code outside string literals. `listen_duration_max <= 0` and
    `= DEFAULT_LISTEN_DURATION` are machinery. Every string literal, though, is
    scanned (docstrings, `Field(description=...)`, CLI help, prompts): we do not
    try to guess which strings reach an agent, because that guess is what went
    wrong before.

IF THIS CHECK FIRES ON YOU, the fix is almost never to exempt yourself — it is
to say the config key instead of the number, or to state the present, articulable
need in prose. Adding an exemption here is a deliberate, reviewable act, which is
the point: the last time this defect shipped, nothing had to be edited at all.

ON A FALSE POSITIVE — the remedy norm, in order

Sometimes the check fires on a true statement that is not advice: an incident
record, a changelog-shaped note, a timing measurement that legitimately puts a
number next to a ceiling token. The remedy is fixed:

  1. **REWORD to break the adjacency.** Say the same true thing without the
     number sitting beside the ceiling token.
  2. **NEVER exempt the path.** A path exemption is a whitelist by another name,
     and it is the first crack that ends this check — the next author's file is
     not on any list, which is the whole reason the check scans by pattern.
  3. **NEVER alter a measurement while rewording.** Evidence is not negotiable;
     if a number is a thing that was observed, it stays, verbatim.

Exemplar (VM-2099, `voice_mode/mcp_shutdown_patch.py`): a measured-incident
table read `17.5s (i.e. to listen_duration_max)`. It is a record, not advice —
and the fix was still a rewording, not an exemption: the cross-reference now
reads "the whole remainder of the listening window described above". Both
measurements were kept verbatim.

THE SCANNED SPACE, STATED (a clean result is only as good as its search space)

Walked from the repo root: `*.md`, `*.markdown`, `*.mdx`, `*.rst`, `*.txt`,
`*.py` (string literals only) and — since VM-2099 `do-002` — `*.json`, `*.yaml`,
`*.yml`, `*.toml`, because agent-facing prompts and tool descriptions increasingly
ship as data files, and a cap suggestion inside one read green until now.
Untracked files are included; ``_SKIP_DIRS`` holds only build/vendor noise.

Two boundaries remain, and neither is closed by widening a suffix list:
  * **Python comments** are not scanned — string literals are. A comment reaches
    no agent.
  * **Prose that never names the parameter** ("listen for up to 45 seconds")
    reads green. The scan is anchored to the ceiling token on purpose; scanning
    every duration in the repo would be unusable, and an unusable check gets
    deleted.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- the scanned space -------------------------------------------------------
# Discovered by walking the tree, NOT by listing files: a new doc dropped in a
# new directory tomorrow is scanned the moment it exists (and before it is even
# committed -- untracked files count too).
#
# The structured-data suffixes are here because an agent-facing surface is
# increasingly a data file: an MCP server manifest, a plugin's tool description,
# a prompt shipped as JSON or YAML. Prose is not the only thing an agent reads,
# and "the check was clean" must mean the same thing tomorrow. See the module
# docstring for the full statement of the scanned space and its two remaining
# boundaries.
_DOC_SUFFIXES = frozenset(
    {".md", ".markdown", ".mdx", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml"}
)
_PY_SUFFIX = ".py"
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

# --- the ceiling token (the floor is deliberately absent -- VM-1168) ---------
# (?<![\w.])  : not the tail of a longer identifier, which is what keeps the
#               config key VOICEMODE_DEFAULT_LISTEN_DURATION and the legacy
#               floor name min_listen_duration out of the match.
# (?!\w)      : ..._min / ..._minimum never match, so floor guidance stays legal.
_CEILING_TOKEN = re.compile(
    r"""
    (?<![\w.])
    (?<!min\ )(?<!minimum\ )(?<!floor\ )      # prose about the floor, skipped
    (?:
        listen(?:ing)?[\ _-]duration(?:[\ _-]max)?
      | max(?:imum)?[\ _-]listen(?:ing)?[\ _-]duration
    )
    (?!\w)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_NUMERAL = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
_DURATION_WITH_UNIT = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s*(?:s\b|secs?\b|seconds?\b|mins?\b|minutes?\b)",
    re.IGNORECASE,
)
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_JSON_UNICODE_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")
# env-file content, i.e. the config's own home -- see the exemption in _scan_text.
_ENV_FILE_CONTENT = re.compile(r"^\s*(?:#\s*)?(?:export\s+)?VOICEMODE_[A-Z0-9_]+=", re.MULTILINE)

# How close a numeral has to sit to the token to read as "this is the value".
# Generous on purpose: `- listen_duration: Max listen time in seconds (default:
# 120)` puts 39 characters between them, and that line was one of the surfaces
# that taught the wrong number.
_NEAR_RADIUS = 60


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    excerpt: str

    def __str__(self) -> str:  # pragma: no cover - reporting only
        return f"{self.path}:{self.line} [{self.rule}] {self.excerpt}"


def _decode_json_escapes(text: str) -> str:
    """Read `\\u2013` as the en-dash it is, so a serialised schema dump and its
    source read identically. See the module docstring on why the dash form must
    not matter."""
    return _JSON_UNICODE_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _excerpt(text: str, offset: int, width: int = 90) -> str:
    start = max(0, offset - width // 3)
    return " ".join(text[start : start + width].split())


def _is_exempt(rel_path: Path) -> bool:
    """Path-level exemptions. Every branch states its reason; see the module
    docstring for the full argument."""
    parts = rel_path.parts
    name = rel_path.name

    # Dated records: history is evidence, not advice.
    if name.upper().startswith("CHANGELOG"):
        return True
    if ".archive" in parts or "archive" in parts:
        return True

    # The config's own home: the number belongs here.
    if name.endswith(".env") or ".env." in name or name.startswith("voicemode.env"):
        return True

    # Test fixtures: usage under test, read by no agent (see docstring for why
    # this does not let a pinned copy of advice hide).
    if parts and parts[0] == "tests":
        return True

    return False


def _iter_scannable_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() not in _DOC_SUFFIXES and path.suffix != _PY_SUFFIX:
            continue
        if _is_exempt(path.relative_to(root)):
            continue
        yield path


def _python_string_literals(source: str) -> List[Tuple[str, int]]:
    """Every string literal in a Python file, with its line number.

    Docstrings, `Field(description=...)`, module-level description constants,
    CLI help text and prompts all land here. We do not classify them: the
    surface that broke last time was a schema field description assigned to a
    module constant, and the next one will be somewhere else again.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - a broken file is another test's job
        return []

    found: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((node.value, node.lineno))
    return found


def _blocks(text: str) -> Iterator[Tuple[str, int]]:
    """Blank-line-separated blocks (the natural unit of a doc paragraph, a
    markdown table, or a bullet list), each with the line it starts on."""
    line_no = 1
    for chunk in re.split(r"\n[ \t]*\n", text):
        yield chunk, line_no
        line_no += chunk.count("\n") + 2


def _md_sections(text: str) -> Iterator[Tuple[str, int]]:
    """Markdown heading sections: heading line plus body up to the next heading
    of the same or higher level. A section headed `### listen_duration_max` is
    *about* the ceiling, so advice a few paragraphs down still belongs to it."""
    lines = text.splitlines()
    heads: List[Tuple[int, int]] = []  # (index, level)
    for i, line in enumerate(lines):
        m = _MD_HEADING.match(line)
        if m:
            heads.append((i, len(m.group(1))))
    for pos, (i, level) in enumerate(heads):
        end = len(lines)
        for j, lvl in heads[pos + 1 :]:
            if lvl <= level:
                end = j
                break
        yield "\n".join(lines[i:end]), i + 1


def _scan_text(text: str, path_label: str, first_line: int = 1, *, markdown: bool = False) -> List[Violation]:
    text = _decode_json_escapes(text)
    violations: List[Violation] = []
    seen_lines: set = set()

    def record(rule: str, chunk: str, chunk_line: int, offset: int) -> None:
        line = first_line + chunk_line - 1 + _line_of(chunk, offset) - 1
        if line in seen_lines:
            return
        seen_lines.add(line)
        violations.append(Violation(path_label, line, rule, _excerpt(chunk, offset)))

    # The scanned unit is the blank-line-separated block: a paragraph, a bullet
    # list, a markdown table, one docstring section. Plus, for markdown, any
    # section whose HEADING names the ceiling -- a section titled
    # `### listen_duration_max` is about the ceiling all the way down, so advice
    # a few paragraphs below the heading still belongs to it. (Only the heading
    # counts: a body mention would make an H1 span the whole document and every
    # unrelated duration in the file would read as ceiling advice.)
    units: List[Tuple[str, int, bool]] = [(c, ln, False) for c, ln in _blocks(text)]
    if markdown:
        units += [
            (c, ln, True)
            for c, ln in _md_sections(text)
            if _CEILING_TOKEN.search(c.splitlines()[0])
        ]

    for chunk, chunk_line, heading_scoped in units:
        # The config's own home, wherever it lives: a block that IS env-file
        # content (`VOICEMODE_...=`) is the number's legitimate place -- both the
        # shipped env template (a string literal inside config.py, not a .env
        # path) and docs showing a user which line to add to voicemode.env. The
        # exemption is by CONTENT, not by filename, so it survives the template
        # moving house.
        if _ENV_FILE_CONTENT.search(chunk):
            continue

        if not heading_scoped:
            # R1 -- a numeral sitting next to the name.
            for match in _CEILING_TOKEN.finditer(chunk):
                window = chunk[max(0, match.start() - _NEAR_RADIUS) : match.end() + _NEAR_RADIUS]
                if _NUMERAL.search(window):
                    record("R1-numeral-near-ceiling", chunk, chunk_line, match.start())

        # R2 -- a duration-with-unit anywhere in a unit that names the ceiling.
        if _CEILING_TOKEN.search(chunk):
            for match in _DURATION_WITH_UNIT.finditer(chunk):
                record("R2-duration-in-ceiling-context", chunk, chunk_line, match.start())

    return violations


def scan_for_cap_teaching(root: Path) -> List[Violation]:
    """Scan a tree for numeric listening-ceiling advice in teaching positions."""
    violations: List[Violation] = []
    for path in _iter_scannable_files(root):
        rel = str(path.relative_to(root))
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == _PY_SUFFIX:
            for literal, lineno in _python_string_literals(text):
                violations.extend(_scan_text(literal, rel, first_line=lineno))
        else:
            violations.extend(_scan_text(text, rel, markdown=True))
    return sorted(violations, key=lambda v: (v.path, v.line, v.rule))


# ---------------------------------------------------------------------------
# The check itself
# ---------------------------------------------------------------------------


def test_no_numeric_ceiling_advice_anywhere_in_the_repo():
    """No surface teaches a listening-ceiling number. This is the check that
    VM-746 lacked and that let VM-1775 reintroduce the defect five months later.
    """
    violations = scan_for_cap_teaching(REPO_ROOT)
    assert not violations, (
        "A numeric listen_duration_max (the listening CEILING) appears in a "
        "teaching position. The user owns the ceiling via "
        "VOICEMODE_DEFAULT_LISTEN_DURATION; documentation that names a number "
        "teaches agents to pass one, which cuts the user off mid-answer "
        "(VM-2099). Name the config key instead of a number, or state the "
        "present need in prose. Findings:\n  "
        + "\n  ".join(str(v) for v in violations)
    )


# ---------------------------------------------------------------------------
# Proving the check can fail (POLICY 4b -- the inversion IS the acceptance).
# Each of these would have caught the real defect; test_..._original_turns_advice
# is the exact text that shipped, and test_..._brand_new_file is the recurrence
# vector a whitelist would have missed.
# ---------------------------------------------------------------------------

_ORIGINAL_TURNS_ADVICE = (
    "Keep surveys short (≤ ~7 ask turns) and give each ask turn a sensible "
    "\"listen_duration_max\" (30–45s for normal questions)."
)


def _write(root: Path, rel: str, body: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def test_check_catches_the_original_turns_advice(tmp_path):
    """(a) The VM-1775 phrasing, verbatim, in the schema-description position it
    actually occupied -- a module constant, not a docstring."""
    _write(
        tmp_path,
        "voice_mode/tools/converse.py",
        "_TURNS_PARAM_DESCRIPTION = (\n    %r\n)\n" % _ORIGINAL_TURNS_ADVICE,
    )
    violations = scan_for_cap_teaching(tmp_path)
    assert violations, "the check must fail on the advice that caused VM-2099"


def test_check_catches_the_original_turns_advice_with_escaped_en_dash(tmp_path):
    """The same advice as it appears on the wire (JSON-escaped en-dash) -- the
    form that false-cleans even an en-dash-aware grep."""
    _write(tmp_path, "docs/schema-dump.md", _ORIGINAL_TURNS_ADVICE.replace("–", "\\u2013"))
    assert scan_for_cap_teaching(tmp_path)


def test_check_catches_a_brand_new_file(tmp_path):
    """(b) The recurrence vector: a file that did not exist at fix time, in a
    directory that did not exist either. A whitelist of the July 2026 surfaces
    fails this test by construction."""
    _write(
        tmp_path,
        "docs/guides/some-feature-invented-later/usage.md",
        "## Asking a question\n\nSet listen_duration_max to 45 for quick questions.\n",
    )
    violations = scan_for_cap_teaching(tmp_path)
    assert violations and "usage.md" in violations[0].path


def test_check_catches_a_prompt_shipped_as_structured_data(tmp_path):
    """The boundary closed by do-002: an agent-facing surface that is a data file
    rather than prose -- a prompt in JSON, a tool description in YAML, defaults in
    TOML. Each read green before the suffix list was widened."""
    _write(
        tmp_path,
        "prompts/survey.json",
        '{"description": "Ask each question with listen_duration_max=45."}\n',
    )
    _write(
        tmp_path,
        "agents/interviewer.yaml",
        "instructions: |\n  Give each turn a listen_duration_max of 30 seconds.\n",
    )
    _write(
        tmp_path,
        "config/tool.toml",
        '[converse]\n# advice, not config: listen_duration_max = 60 is plenty\n',
    )
    found = {v.path for v in scan_for_cap_teaching(tmp_path)}
    assert found == {"prompts/survey.json", "agents/interviewer.yaml", "config/tool.toml"}


def test_check_catches_an_example_call_in_a_new_docstring(tmp_path):
    _write(
        tmp_path,
        "voice_mode/tools/something_new.py",
        'def ask():\n    """Ask a thing.\n\n    converse("How was it?", listen_duration_max=45)\n    """\n',
    )
    assert scan_for_cap_teaching(tmp_path)


def test_check_catches_advice_a_few_lines_below_the_heading(tmp_path):
    """R2: the number need not sit on the same line as the name."""
    _write(
        tmp_path,
        "docs/reference/params.md",
        "### listen_duration_max\n\nThe tool handles silence detection well.\n\n"
        "**When to override:**\n- Response will be exceptionally long (>120s)\n",
    )
    assert scan_for_cap_teaching(tmp_path)


def test_check_allows_naming_the_config_key(tmp_path):
    """The cure must be expressible: say the key, never a number."""
    _write(
        tmp_path,
        "docs/reference/params.md",
        "### listen_duration_max\n\n**Type:** number (default: the user's "
        "`VOICEMODE_DEFAULT_LISTEN_DURATION`)\nLeave it unset; the user's config "
        "owns the ceiling. Override only for a need you can state.\n",
    )
    assert scan_for_cap_teaching(tmp_path) == []


def test_check_allows_floor_guidance(tmp_path):
    """VM-1168's protected direction: a floor cannot cut an answer short, so
    numbers for listen_duration_min stay legal."""
    _write(
        tmp_path,
        "docs/reference/params.md",
        "### listen_duration_min\n\n**Type:** number (default: 2.0 seconds)\n\n"
        "Raise it to 15 seconds after reading a long list, so the user gets "
        "thinking time. Minimum listen duration of 3 seconds is also fine.\n",
    )
    assert scan_for_cap_teaching(tmp_path) == []


def test_check_ignores_dated_records_and_the_config_home(tmp_path):
    _write(tmp_path, "CHANGELOG.md", "- Changed default listen_duration from 45s to 120s\n")
    _write(tmp_path, "docs/.archive/old-prompt.md", "Set listen_duration=120 for surveys.\n")
    _write(tmp_path, "config/voicemode.env.example", "VOICEMODE_DEFAULT_LISTEN_DURATION=300\n")
    assert scan_for_cap_teaching(tmp_path) == []


def test_check_ignores_functional_code_and_test_fixtures(tmp_path):
    _write(
        tmp_path,
        "voice_mode/tools/converse.py",
        "DEFAULT = 120.0\n\n\ndef f(listen_duration_max: float = DEFAULT):\n"
        "    if listen_duration_max <= 0:\n        raise ValueError('positive')\n",
    )
    _write(
        tmp_path,
        "tests/test_something.py",
        'def test_it():\n    assert call(listen_duration_max=45) == 45\n',
    )
    assert scan_for_cap_teaching(tmp_path) == []

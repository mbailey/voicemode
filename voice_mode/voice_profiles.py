"""Voice profiles for clone-based TTS.

Voices live in ``$VOICEMODE_VOICES_DIR`` (default ``~/.voicemode/voices``).
Each subdirectory is a voice profile. For ``<name>/`` we look for a
``default.wav`` (or the first ``*.wav``) plus a sidecar transcript
``default.txt`` (or matching basename). SuperDirt-style: drop a folder in,
you get a voice. Symlink ``default.wav`` to swap which sample is active
without renaming files.

Each profile maps a voice name to a reference audio file and transcript,
plus model and endpoint routing info.

Voice expression syntax (``voice="<expr>"`` at converse time):

* ``samantha``           — the voice's ``default.wav``
* ``samantha[0]``        — the first ``*.wav`` in the dir (sorted)
* ``samantha[2]``        — the third ``*.wav`` (SuperDirt-style indexing)
* ``samantha/angry.wav`` — an explicit file inside the voice dir
* ``group/samantha``     — a group-qualified voice path (VM-1901)
* ``group/samantha[2]`` / ``group/samantha/angry.wav`` — qualified + selector
* ``group``              — a *cast* (a group that declares a ``default:``
  member in its ``voice.md``); resolves to that member, recursively
* ``/abs/path.wav``      — absolute path passed straight to the TTS server
* ``./clip.wav``         — path relative to the CWD (also ``../`` and ``~/``);
  expanded to an absolute path before it reaches the server

Remote TTS servers (e.g. mlx-audio on ms2) need the ref_audio path that
exists on *their* filesystem, not ours. Set ``VOICEMODE_REMOTE_VOICES_DIR``
to the path where the voices directory is mirrored on the TTS host; we
rewrite the prefix when sending the request. If unset, the local
absolute path is sent (only useful when the TTS server runs locally).

Resolution contract (VM-1901 design.md)
----------------------------------------
:func:`resolve_voice` is **total**: it either returns a fully-populated,
frozen :class:`VoiceResolution` or it raises a :class:`VoiceResolutionError`
subclass. No voice expression is ever silently substituted with a different
provider's default voice (the "alloy fallback" bug) — every failure mode
names the alternatives. See ``design.md`` in the VM-1901 task dir for the
full precedence order and rationale.

``get_profile`` / ``is_clone_voice`` / ``parse_voice_expr`` remain for
back-compat with existing callers that want the old "return None/False on
failure" contract (e.g. enumeration code that must never raise). New calling
code — in particular the TTS failover path — should call
:func:`resolve_voice` directly so an unresolvable expression is caught
*before* any network request, per P1 of the design.
"""

import difflib
import logging
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger("voicemode")

VOICES_DIR = Path(os.path.expanduser(
    os.environ.get("VOICEMODE_VOICES_DIR", "~/.voicemode/voices")
))

# Path on the remote TTS server where VOICES_DIR is mirrored. When set,
# ref_audio paths sent to the server are rewritten with this prefix so
# the server can find the file on its own filesystem.
REMOTE_VOICES_DIR = os.environ.get("VOICEMODE_REMOTE_VOICES_DIR", "")

# Default mlx-audio endpoint for impressions (Qwen3-TTS).
# Defaults to a local mlx-audio server. Override via env vars when you
# want to point at a different host (e.g. a remote ms2 box on the LAN).
DEFAULT_CLONE_BASE_URL = os.environ.get(
    "VOICEMODE_MLX_AUDIO_BASE_URL",
    "http://127.0.0.1:8890/v1",
)
# 1.7B-Base-4bit: ~2× realtime on M-series, clean audio, ~2.2GB on disk.
# Picked as the default from the Apr 2026 quant matrix bench. The
# auto-generated voicemode.env lists alternatives (5-bit, 6-bit, bf16,
# 0.6B-5bit). Shares resolution with voice_mode.config.CLONE_MODEL.
from voice_mode.config import CLONE_MODEL as DEFAULT_CLONE_MODEL

# Matches ``name[0]``, ``name[12]`` as the FINAL path segment. Forbids
# further ``/``/``[``/``]`` inside the name so it only ever consumes one
# segment's trailing index (see :func:`_split_index_suffix`).
_INDEX_RE = re.compile(r"^([^/\[\]]+)\[(\d+)\]$")

# Undeclared-group ("cast") severity switch — VM-1901 fix-001, fenced pending
# Mike (design.md §7 escalation). Day one ships with 32 groups and ZERO
# declared defaults, so the hard-error default would make `voice=blackadder`
# (the voice Mike adopted the morning of 2026-07-25 to fix an identity
# collision) fail to resolve. "error" is the designed behaviour and stays the
# default; "warn" is a one-release escape hatch: an undeclared group logs a
# WARNING and resolves to its alphabetically-first member (never a different
# provider's voice — the blast radius stays inside the cast) instead of
# raising. Read at call time (not cached) so it can be flipped without a
# process restart.
UNDECLARED_GROUP_SEVERITY_ENV = "VOICEMODE_CAST_UNDECLARED_SEVERITY"

# Provider-native whitelist (design.md §3.2.6), checked LAST and explicitly.
# OpenAI's six original TTS voices (tts-1 / tts-1-hd). Kept as its own
# constant, deliberately narrower than voices.OPENAI_TTS_VOICES (which also
# lists newer gpt-4o-mini-tts-only voices for enumeration purposes) so this
# whitelist matches simple_failover's existing openai_voices mapping table
# 1:1 — extending it is a separate concern from this fix.
OPENAI_NATIVE_VOICES = frozenset({"alloy", "echo", "fable", "nova", "onyx", "shimmer"})

# Kokoro voice names simple_failover.py knows how to map onto an OpenAI
# equivalent when a mixed TTS_BASE_URLS chain fails over to OpenAI. Naming a
# name in this set is legitimate provider-native usage, not an unresolved
# reference — kept as a single source of truth so voice_profiles' whitelist
# and simple_failover's mapping table can't drift apart silently.
KOKORO_MAPPED_VOICES = frozenset({
    "af_sky", "af_sarah", "af_alloy", "am_adam", "am_echo", "am_onyx", "bm_fable",
})


@dataclass
class VoiceProfile:
    """A voice cloning profile."""
    name: str
    ref_audio: str       # Absolute path to reference audio (server-side)
    ref_text: str        # Transcript of reference audio
    model: str           # TTS model to use
    base_url: str        # TTS endpoint URL
    description: str = ""
    voice_dir: str = ""  # Absolute path to the voice's own directory


@dataclass(frozen=True)
class VoiceResolution:
    """The total, structural result of resolving a voice expression.

    ``resolved`` is STRUCTURALLY IMPOSSIBLE to populate with a value that
    did not pass through :func:`resolve_voice` — there is no code path that
    constructs one for an unresolvable expression; failure always raises a
    :class:`VoiceResolutionError` instead. This is the fix for
    ``converse.py``'s ``resolved_voice`` variable, which was never resolved.
    """
    requested: str                    # verbatim caller expression
    resolved: str                     # canonical id / provider name — what will actually sound
    kind: str                         # "clone" | "provider" | "clip"
    via: str                          # "leaf" | "qualified" | "cast-default:<chain>" |
                                       #   "index[N]" | "file-selector" | "provider-native" | "path-escape"
    profile: Optional[VoiceProfile] = None


class VoiceResolutionError(Exception):
    """Base class for every :func:`resolve_voice` failure.

    Every subclass carries a loud, specific, actionable message — per P1 of
    design.md, there is no way to fail silently. Never caught-and-defaulted
    to a provider voice; callers that need old best-effort semantics use
    :func:`get_profile` / :func:`is_clone_voice` instead.
    """


class Unresolvable(VoiceResolutionError):
    """Nothing matched — a leaf, a group, or the provider-native whitelist."""

    def __init__(self, expr: str, detail: str, nearest: Optional[List[str]] = None):
        self.expr = expr
        self.detail = detail
        self.nearest = nearest or []
        msg = f"Unresolvable voice {expr!r}: {detail}."
        if self.nearest:
            msg += f" Did you mean: {', '.join(self.nearest)}?"
        msg += " See `voicemode voices list`."
        super().__init__(msg)


class AmbiguousLeaf(VoiceResolutionError):
    """A bare leaf name matches two or more canonical ids."""

    def __init__(self, expr: str, name: str, candidates: List[str]):
        self.expr = expr
        self.name = name
        self.candidates = candidates
        super().__init__(
            f"Ambiguous voice {name!r} in {expr!r}: matches {len(candidates)} entries "
            f"({', '.join(candidates)}). Use a qualified form, e.g. {candidates[0]!r}."
        )


class NotACast(VoiceResolutionError):
    """A group was named but has no declared ``default:`` — not yet a cast."""

    def __init__(self, expr: str, group: str, members: List[str]):
        self.expr = expr
        self.group = group
        self.members = members
        label = group or "<voices root>"
        members_str = ", ".join(members) if members else "(no members)"
        hint = (
            f" Declare one: `voicemode cast set-default {label} <member>` "
            f"(writes {label}/voice.md's `default:` field), or address a member "
            f"directly (e.g. {label}/{members[0]})."
            if members else ""
        )
        super().__init__(
            f"{label!r} is a group of {len(members)} voice(s) but declares no "
            f"default — not yet a cast. Members: {members_str}.{hint}"
        )


class CastDefaultMissing(VoiceResolutionError):
    """A cast's declared default names a member that doesn't exist."""

    def __init__(self, expr: str, group: str, declared: str, members: List[str]):
        self.expr = expr
        self.group = group
        self.declared = declared
        self.members = members
        members_str = ", ".join(members) if members else "(no members)"
        super().__init__(
            f"Cast {group!r}'s declared default {declared!r} does not exist. "
            f"Actual members: {members_str}. Fix {group}/voice.md's `default:` field."
        )


class IndexOutOfRange(VoiceResolutionError):
    """``name[N]`` where N is outside the available sample range."""

    def __init__(self, expr: str, canon: str, index: int, count: int):
        self.expr = expr
        self.canon = canon
        self.index = index
        self.count = count
        if count:
            range_str = f"valid range 0-{count - 1}"
        else:
            range_str = "no samples available"
        super().__init__(
            f"Sample index {index} out of range for {canon!r} in {expr!r}: "
            f"{count} sample(s) available ({range_str})."
        )


class BadSelector(VoiceResolutionError):
    """A file selector or path segment shape that doesn't make sense."""

    def __init__(self, expr: str, detail: str):
        self.expr = expr
        self.detail = detail
        super().__init__(f"Bad selector in {expr!r}: {detail}")


@dataclass
class _Registry:
    """Internal load-time state — replaces the flat leaf-keyed dict."""
    profiles: Dict[str, VoiceProfile] = field(default_factory=dict)          # canonical id -> profile
    leaf_index: Dict[str, List[str]] = field(default_factory=dict)           # voice leaf -> [canonical id]
    group_children: Dict[str, Dict[str, str]] = field(default_factory=dict)  # group canon -> {child_name: "voice"|"group"|"sample_bin"}
    group_default: Dict[str, Optional[str]] = field(default_factory=dict)    # group canon -> declared default leaf (or None)
    group_leaf_index: Dict[str, List[str]] = field(default_factory=dict)     # group leaf -> [group canonical id]
    sample_bins: Dict[str, str] = field(default_factory=dict)                # sample-bin canon -> hint wav filename
    sample_bin_leaf_index: Dict[str, List[str]] = field(default_factory=dict)  # sample-bin leaf -> [canonical id]


_registry = _Registry()
_loaded = False


def _resolve_default_wav(voice_dir: Path) -> Optional[Path]:
    """Pick the reference WAV inside a voice directory.

    Order of preference:
    1. ``default.wav`` (file or symlink) — the explicit default
    2. The single ``*.wav`` if there's only one — unambiguous

    Directories with multiple WAVs and no ``default.wav`` are treated as
    sample bins, not voices, and skipped. Add a ``default.wav`` symlink
    if you want such a directory to register as a voice.
    """
    default = voice_dir / "default.wav"
    if default.exists():
        return default

    wavs = sorted(voice_dir.glob("*.wav"))
    if not wavs:
        return None
    if len(wavs) == 1:
        return wavs[0]

    # VM-1901 mouth 4: this used to log at DEBUG only, which meant the skip
    # was invisible at any level an operator would normally run at. WARNING
    # names the cure directly.
    logger.warning(
        f"Skipping {voice_dir.name!r}: {len(wavs)} WAVs and no default.wav "
        f"(treated as a sample bin, not a voice — add a default.wav symlink "
        f"to register it, e.g. `ln -s {wavs[0].name} default.wav`)."
    )
    return None


def _sample_bin_hint(voice_dir: Path) -> Optional[str]:
    """Return the first ``*.wav`` filename if ``voice_dir`` is a sample bin
    (>= 2 WAVs, no ``default.wav``) — the same condition
    :func:`_resolve_default_wav` already WARNs about at load time.

    Used to register a resolve-time marker (design.md §3.3: mouth 4 must be
    "closed loudly at both ends") so a caller who directly names a sample-bin
    directory gets the specific cure in the *error*, not just in a load-time
    log line they may never have seen.
    """
    if (voice_dir / "default.wav").exists():
        return None
    wavs = sorted(voice_dir.glob("*.wav"))
    return wavs[0].name if len(wavs) >= 2 else None


def _resolve_transcript(wav_path: Path) -> str:
    """Read the matching transcript for a reference WAV.

    Resolution order:

    1. ``<basename>.txt`` sidecar next to the WAV.
    2. ``default.txt`` sidecar in the same directory.
    3. the ``transcript`` field of a ``voice.md`` frontmatter in the same
       directory — the layout ``voicemode clone add`` writes (VM-1439). This
       lazily repairs voice.md-only profiles (those created before clone add
       also wrote a ``default.txt``) so they resolve a non-empty ref_text with
       no migration step.

    Returns empty string if no transcript is found (caller will warn).
    """
    same_name = wav_path.with_suffix(".txt")
    if same_name.exists():
        return same_name.read_text().strip()

    fallback = wav_path.parent / "default.txt"
    if fallback.exists():
        return fallback.read_text().strip()

    return _transcript_from_voice_md(wav_path.parent / "voice.md")


def _extract_frontmatter(text: str) -> Optional[str]:
    """Return the YAML frontmatter delimited by the first two ``---`` fences.

    Returns ``None`` if ``text`` doesn't open with a ``---`` fence or the
    closing fence is missing.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    return None


def _transcript_from_voice_md(voice_md: Path) -> str:
    """Read the ``transcript`` field from a ``voice.md`` frontmatter.

    ``voicemode clone add`` records the reference transcript in the voice.md
    YAML frontmatter (``transcript:``). Reading it here lets the loader
    resolve a non-empty ref_text for cloned voices that have no ``.txt``
    sidecar. Returns empty string when the file is missing, has no
    frontmatter, or has no usable ``transcript`` field.
    """
    if not voice_md.exists():
        return ""
    try:
        front = _extract_frontmatter(voice_md.read_text())
    except OSError:
        return ""
    if front is None:
        return ""
    try:
        data = yaml.safe_load(front)
    except yaml.YAMLError:
        return ""
    if not isinstance(data, dict):
        return ""
    transcript = data.get("transcript")
    if not isinstance(transcript, str):
        return ""
    return transcript.strip()


def _read_group_default(group_dir: Path) -> Optional[str]:
    """Read the ``default:`` key from a group's ``voice.md`` frontmatter.

    This is what promotes a plain ``group`` to a ``cast`` (VM-1901 design.md
    §4) — declaration, not child count. Returns ``None`` (undeclared) when
    the file is absent, has no frontmatter, or has no usable ``default``
    field; the group-level ``voice.md`` has no ``transcript:`` key so it
    never interferes with per-voice transcript resolution.
    """
    voice_md = group_dir / "voice.md"
    if not voice_md.exists():
        return None
    try:
        front = _extract_frontmatter(voice_md.read_text())
    except OSError:
        return None
    if front is None:
        return None
    try:
        data = yaml.safe_load(front)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    default = data.get("default")
    if not isinstance(default, str) or not default.strip():
        return None
    return default.strip()


def _read_description(voice_dir: Path) -> str:
    """Read the optional ``description.txt`` sidecar."""
    desc_path = voice_dir / "description.txt"
    if desc_path.exists():
        return desc_path.read_text().strip()
    return ""


def _derive_group(voice_dir: Path) -> str:
    """Joined relative path from ``VOICES_DIR`` to ``voice_dir.parent``.

    Returns the empty string for a top-level voice dir. For a multi-level
    nested voice (``star-trek/tng/picard``) the full lineage is preserved
    (``star-trek/tng``), not just the immediate parent.
    """
    rel_parent = voice_dir.parent.relative_to(VOICES_DIR)
    s = rel_parent.as_posix()
    return "" if s == "." else s


def _format_description(base_desc: str, group: str) -> str:
    """Append ``(from <group>)`` as a footer on its own line.

    Top-level voices (empty ``group``) keep their description unchanged.
    Voices with no ``description.txt`` get just the suffix.
    """
    if not group:
        return base_desc
    suffix = f"(from {group})"
    if not base_desc:
        return suffix
    return f"{base_desc}\n{suffix}"


def _canonical_id(path: Path) -> str:
    """The registry key for a voice or group dir: its path relative to
    ``VOICES_DIR``, POSIX-separated (``laurie``, ``secretary/lee-holloway``,
    ``star-trek/tng/picard``). This is the single change (design.md §3.1)
    that makes qualified addressing, collision handling and the
    requested/resolved recording contract all fall out."""
    return path.relative_to(VOICES_DIR).as_posix()


def _build_profile(voice_dir: Path, wav: Path) -> VoiceProfile:
    """Construct a VoiceProfile for a directory that qualifies as a voice."""
    transcript = _resolve_transcript(wav)
    if not transcript:
        logger.warning(
            f"Voice {voice_dir.name!r}: no transcript found "
            f"(expected {wav.with_suffix('.txt').name} or default.txt). "
            f"ref_text will be empty."
        )

    base_desc = _read_description(voice_dir)
    group = _derive_group(voice_dir)
    return VoiceProfile(
        name=voice_dir.name,
        ref_audio=_translate_path(wav),
        ref_text=transcript,
        model=DEFAULT_CLONE_MODEL,
        base_url=DEFAULT_CLONE_BASE_URL,
        description=_format_description(base_desc, group),
        voice_dir=str(voice_dir),
    )


def _is_dot_dir(path: Path) -> bool:
    return path.name.startswith(".")


def _has_voice_like_content(path: Path) -> bool:
    """True if ``path`` is (or contains, recursively) something that would
    register as a voice — used only for the unreachable-subdir lint below."""
    if _resolve_default_wav(path) is not None:
        return True
    try:
        children = [p for p in path.iterdir() if p.is_dir() and not _is_dot_dir(p)]
    except OSError:
        return False
    return any(_has_voice_like_content(c) for c in children)


def _load_dir_profiles() -> _Registry:
    """Walk VOICES_DIR recursively and build the resolver's registry.

    A directory containing a resolvable WAV (see :func:`_resolve_default_wav`)
    is a voice; otherwise, if it has visible (non-dot) subdirectories, it's a
    group and we descend into it. Subdirectories of a voice dir are NOT
    walked further — voices and groups are disjoint by construction.

    Voices are keyed by their CANONICAL id (path relative to VOICES_DIR), not
    by leaf name — a leaf index sits on top for bare-name addressing. Two
    voices sharing a leaf name both register (their qualified forms work);
    the leaf index records the collision so a bare, ambiguous lookup raises
    :class:`AmbiguousLeaf` instead of the old load-time drop-both.

    Dot-directories (``.samples``, ``.notes``, ...) are never walked, never
    registered, never listed — closes a latent phantom-voice hazard (the
    old walk had no dotfile filter and would happily register anything
    living inside a group's dot-dir).
    """
    reg = _Registry()
    conflicts: Dict[str, List[str]] = {}

    if not VOICES_DIR.exists() or not VOICES_DIR.is_dir():
        logger.debug(f"Voices directory not found at {VOICES_DIR}")
        return reg

    def register_child(parent_canon: str, name: str, kind: str) -> None:
        reg.group_children.setdefault(parent_canon, {})[name] = kind

    def walk(dir_path: Path, parent_canon: str) -> None:
        wav = _resolve_default_wav(dir_path)
        if wav is not None:
            canon = _canonical_id(dir_path)
            leaf = dir_path.name
            if leaf in reg.leaf_index:
                conflicts.setdefault(leaf, list(reg.leaf_index[leaf])).append(canon)
            reg.leaf_index.setdefault(leaf, []).append(canon)
            reg.profiles[canon] = _build_profile(dir_path, wav)
            register_child(parent_canon, leaf, "voice")

            # Lint: a voice dir with visible, voice-like subdirs is
            # unreachable (voices and groups are disjoint by design) —
            # today's walk stops here, so say so loudly instead of quietly
            # dropping content on the floor.
            try:
                visible = [p for p in dir_path.iterdir() if p.is_dir() and not _is_dot_dir(p)]
            except OSError:
                visible = []
            for sub in visible:
                if _has_voice_like_content(sub):
                    logger.warning(
                        f"{canon!r} is a voice but contains voice-like subdir "
                        f"{sub.name!r} — unreachable (voices and groups are "
                        f"disjoint by design). Move {sub.name!r} out of "
                        f"{canon!r} or remove {canon!r}'s top-level wavs."
                    )
            return  # do NOT descend into a voice dir

        try:
            children = sorted(
                p for p in dir_path.iterdir() if p.is_dir() and not _is_dot_dir(p)
            )
        except OSError:
            return
        if not children:
            # Either a genuinely empty dir, or a sample bin (>=2 WAVs, no
            # default.wav — already WARNED about above). Register the latter
            # so a direct resolve-time request for its name gets the same
            # specific cure in the error, not just a generic "unresolvable"
            # (design.md §3.3: mouth 4 closed loudly at BOTH ends).
            bin_hint = _sample_bin_hint(dir_path)
            if bin_hint is not None:
                canon = _canonical_id(dir_path)
                leaf = dir_path.name
                reg.sample_bins[canon] = bin_hint
                reg.sample_bin_leaf_index.setdefault(leaf, []).append(canon)
                register_child(parent_canon, leaf, "sample_bin")
            return

        this_canon = _canonical_id(dir_path)
        reg.group_default[this_canon] = _read_group_default(dir_path)
        reg.group_leaf_index.setdefault(dir_path.name, []).append(this_canon)
        register_child(parent_canon, dir_path.name, "group")
        for child in children:
            walk(child, this_canon)

    for top in sorted(p for p in VOICES_DIR.iterdir() if p.is_dir() and not _is_dot_dir(p)):
        walk(top, "")

    for leaf, canons in conflicts.items():
        logger.warning(
            f"Voice leaf {leaf!r} is ambiguous — appears at {canons}. Bare "
            f"{leaf!r} raises AmbiguousLeaf at resolve time; use a qualified "
            f"form ({canons[0]!r}, ...) to address one directly."
        )

    if reg.profiles:
        logger.info(
            f"Loaded {len(reg.profiles)} voice profiles from {VOICES_DIR}: "
            f"{sorted(reg.profiles.keys())}"
        )
    return reg


def load_profiles() -> Dict[str, VoiceProfile]:
    """Load voice profiles by scanning VOICES_DIR.

    Returns the canonical-id-keyed profile dict (also stored for
    :func:`resolve_voice` et al). Kept for back-compat — most callers just
    want ``len()``/iteration, not lookup, so the rekeying (VM-1901) rarely
    matters to them; anything doing bare-name lookup should go through
    :func:`get_profile` / :func:`resolve_voice` instead of indexing this
    dict directly.
    """
    global _registry, _loaded
    _registry = _load_dir_profiles()
    _loaded = True
    return _registry.profiles


def _ensure_loaded() -> None:
    if not _loaded:
        load_profiles()


def parse_voice_expr(expr: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse a voice expression into ``(voice_name, selector)``.

    Kept for back-compat with existing callers/tests. This is the OLD,
    single-segment parser — :func:`resolve_voice` implements the full
    (group-qualified, cast-aware) precedence order per design.md §3.2 and
    does not call this function. Selector is either ``None`` (use default),
    a string like ``"[N]"`` (indexed sample), or a relative file path inside
    the voice dir (e.g. ``"angry.wav"``). For a filesystem path the
    voice_name is ``None`` and the selector is the path itself.

    Filesystem paths are recognised when the expression starts with a
    path marker — ``/`` (absolute), ``./`` or ``../`` (relative to the
    CWD), or ``~`` (home). Relative and home forms are expanded and made
    absolute against the CWD so the rest of the pipeline — and the TTS
    server — always sees a concrete path. We use ``os.path.abspath``
    (lexical) rather than ``Path.resolve()`` so a symlinked
    ``default.wav`` is preserved: resolving the symlink would change
    which sidecar transcript (``<basename>.txt``) we pick up.

    A bare ``name/file.wav`` (no leading ``./``) stays the
    profile-selector form, so the path markers don't collide with it.

    Examples::

        parse_voice_expr("samantha")           == ("samantha", None)
        parse_voice_expr("samantha[0]")        == ("samantha", "[0]")
        parse_voice_expr("samantha/angry.wav") == ("samantha", "angry.wav")
        parse_voice_expr("/abs/path.wav")      == (None, "/abs/path.wav")
        parse_voice_expr("./clip.wav")         == (None, "/cwd/clip.wav")
        parse_voice_expr("~/clip.wav")         == (None, "/home/clip.wav")
    """
    if not expr:
        return None, None
    if expr.startswith("/"):
        return None, expr
    # Explicit-relative (./, ../) and home (~) paths → expand to an
    # absolute path and hand off to the absolute-path escape hatch.
    if expr.startswith(("./", "../", "~")):
        return None, os.path.abspath(os.path.expanduser(expr))

    m = _INDEX_RE.match(expr)
    if m:
        return m.group(1), f"[{m.group(2)}]"

    if "/" in expr:
        head, _, tail = expr.partition("/")
        return head, tail

    return expr, None


def _list_samples(voice_dir: Path) -> List[Path]:
    """Sorted list of ``*.wav`` files inside a voice directory."""
    return sorted(voice_dir.glob("*.wav"))


def _translate_path(local_path: Path) -> str:
    """Translate a local voices-dir path into the path the TTS server sees.

    If ``VOICEMODE_REMOTE_VOICES_DIR`` is set and ``local_path`` lives
    under ``VOICES_DIR``, replace the prefix. Otherwise return the local
    absolute path (correct when the TTS server is the local machine).
    """
    abs_local = local_path.resolve() if local_path.exists() else local_path
    if not REMOTE_VOICES_DIR:
        return str(abs_local)

    try:
        rel = abs_local.relative_to(VOICES_DIR.resolve())
    except ValueError:
        # Path isn't under VOICES_DIR — pass through untranslated
        return str(abs_local)

    return str(Path(REMOTE_VOICES_DIR) / rel)


# ---------------------------------------------------------------------------
# resolve_voice() — the total resolver (VM-1901 design.md §3)
# ---------------------------------------------------------------------------

def _split_index_suffix(expr: str) -> Tuple[str, Optional[int]]:
    """Split a trailing ``[N]`` off the expression's FINAL path segment.

    Works whether or not the expression is group-qualified: both
    ``fleabag[2]`` and ``secretary/lee-holloway[2]`` split correctly
    (design.md §3.2.2 — the index applies after the walk, to whatever the
    final segment resolves to).
    """
    if "/" in expr:
        head, _, tail = expr.rpartition("/")
        m = _INDEX_RE.match(tail)
        if m:
            return f"{head}/{m.group(1)}", int(m.group(2))
        return expr, None
    m = _INDEX_RE.match(expr)
    if m:
        return m.group(1), int(m.group(2))
    return expr, None


def _undeclared_group_severity() -> str:
    val = os.environ.get(UNDECLARED_GROUP_SEVERITY_ENV, "error").strip().lower()
    return val if val in ("error", "warn") else "error"


def _finalize_voice(expr: str, canon: str, via: str, index: Optional[int]) -> VoiceResolution:
    profile = _registry.profiles[canon]
    if index is None:
        return VoiceResolution(requested=expr, resolved=canon, kind="clone", via=via, profile=profile)

    voice_dir = Path(profile.voice_dir) if profile.voice_dir else VOICES_DIR / canon
    samples = _list_samples(voice_dir)
    if index < 0 or index >= len(samples):
        raise IndexOutOfRange(expr, canon, index, len(samples))
    wav = samples[index]
    indexed_profile = replace(
        profile,
        ref_audio=_translate_path(wav),
        ref_text=_resolve_transcript(wav),
    )
    return VoiceResolution(
        requested=expr, resolved=canon, kind="clone",
        via=f"{via}+index[{index}]", profile=indexed_profile,
    )


def _finalize_file_selector(expr: str, canon: str, filename: str) -> VoiceResolution:
    profile = _registry.profiles[canon]
    voice_dir = Path(profile.voice_dir) if profile.voice_dir else VOICES_DIR / canon
    wav = voice_dir / filename
    if not wav.exists():
        # Not total-strictness-worthy: mirrors the pre-VM-1901 behaviour for
        # a remote TTS host where the file exists on the server but not
        # locally. Still logs loudly, per this task's "never silent" bar.
        logger.warning(
            f"Voice expr {expr!r}: {wav} does not exist locally — "
            f"sending path to server anyway in case it's mirrored."
        )
    new_profile = replace(
        profile,
        ref_audio=_translate_path(wav),
        ref_text=_resolve_transcript(wav) if wav.exists() else "",
    )
    return VoiceResolution(requested=expr, resolved=canon, kind="clone", via="file-selector", profile=new_profile)


def _resolve_cast(expr: str, group_canon: str) -> VoiceResolution:
    """Resolve a (possibly multi-level) cast default chain, depth-capped at 5.

    Cycles are structurally impossible via real directory nesting (a
    default always names a subdirectory, so the chain can only go deeper) —
    the depth cap is the defensive backstop for the one way a "cycle" could
    still occur (a symlink loop under VOICES_DIR), and it doubles as the
    total-resolution safety valve design.md asks for.
    """
    chain_names: List[str] = []
    current = group_canon
    for _ in range(6):  # 5 real hops + 1 to detect overflow
        members = sorted(_registry.group_children.get(current, {}).keys())
        default_leaf = _registry.group_default.get(current)
        warn_mode_used = False

        if not default_leaf:
            if _undeclared_group_severity() == "warn" and members:
                default_leaf = members[0]
                warn_mode_used = True
                logger.warning(
                    f"{current!r} is a group of {len(members)} voice(s) with no "
                    f"declared default ({UNDECLARED_GROUP_SEVERITY_ENV}=warn) — "
                    f"resolving to {default_leaf!r} arbitrarily. Declare a real "
                    f"default before relying on this: voicemode cast set-default "
                    f"{current} <member>."
                )
            else:
                raise NotACast(expr, current, members)

        child_kind = _registry.group_children.get(current, {}).get(default_leaf)
        if child_kind is None:
            raise CastDefaultMissing(expr, current, default_leaf, members)

        chain_names.append(default_leaf)
        child_canon = f"{current}/{default_leaf}" if current else default_leaf

        if child_kind == "voice":
            via = "cast-default:" + "→".join(chain_names)
            if warn_mode_used:
                via += "(undeclared,warn-mode)"
            return _finalize_voice(expr, child_canon, via=via, index=None)

        current = child_canon

    raise Unresolvable(
        expr,
        f"cast default chain exceeds max depth (5): {' -> '.join(chain_names)}",
    )


def _sample_bin_error(expr: str, canon: str) -> Unresolvable:
    """The specific-cure error for naming a sample-bin dir directly.

    design.md §3.3: mouth 4 must be closed loudly at BOTH ends — the
    load-time WARNING already names the cure; this gives the resolve-time
    error the same specific cure instead of a generic "unresolvable".
    """
    hint = _registry.sample_bins[canon]
    return Unresolvable(
        expr,
        f"{canon!r} is a sample bin (multiple WAVs, no default.wav) — add a "
        f"default.wav symlink to register it, e.g. `ln -s {hint} default.wav`",
    )


def _resolve_segment_walk(expr: str, body: str, index: Optional[int]) -> VoiceResolution:
    segments = body.split("/")
    cur_group = ""
    for i, seg in enumerate(segments):
        if not seg:
            raise BadSelector(expr, "empty path segment (double slash?)")
        remaining = segments[i + 1:]
        child_kind = _registry.group_children.get(cur_group, {}).get(seg)
        if child_kind is None:
            existing = sorted(_registry.group_children.get(cur_group, {}).keys())
            where = cur_group or "<voices root>"
            raise Unresolvable(
                expr,
                f"no {seg!r} under {where} — it has: {', '.join(existing) if existing else '(nothing)'}",
            )
        child_canon = f"{cur_group}/{seg}" if cur_group else seg

        if child_kind == "sample_bin":
            raise _sample_bin_error(expr, child_canon)

        if child_kind == "voice":
            if not remaining:
                via = "qualified" if "/" in body else "leaf"
                return _finalize_voice(expr, child_canon, via=via, index=index)
            if len(remaining) > 1:
                raise BadSelector(
                    expr,
                    f"{child_canon!r} is a voice; only one file-selector segment "
                    f"is allowed after it, got {len(remaining)}: {'/'.join(remaining)}",
                )
            if index is not None:
                raise BadSelector(
                    expr,
                    f"{child_canon!r}/{remaining[0]} combines a file selector with "
                    f"an index — pick one addressing form",
                )
            return _finalize_file_selector(expr, child_canon, remaining[0])

        # group
        if not remaining:
            if index is not None:
                raise BadSelector(expr, f"{child_canon!r} is a group; an index selector needs a resolved voice")
            return _resolve_cast(expr, child_canon)
        cur_group = child_canon

    raise Unresolvable(expr, "empty expression")  # pragma: no cover — defensive


def _nearest_matches(name: str, limit: int = 5) -> List[str]:
    candidates = sorted(set(_registry.leaf_index.keys()) | set(_registry.group_leaf_index.keys()))
    return difflib.get_close_matches(name, candidates, n=limit)


def _is_provider_native(name: str) -> bool:
    if name in OPENAI_NATIVE_VOICES or name in KOKORO_MAPPED_VOICES:
        return True
    try:
        from . import config as _vm_config
        if name in getattr(_vm_config, "TTS_VOICES", ()):
            return True
    except Exception:  # pragma: no cover — never let a config import break resolution
        pass
    return False


def _resolve_bare(expr: str, name: str, index: Optional[int]) -> VoiceResolution:
    voice_candidates = _registry.leaf_index.get(name, [])
    if len(voice_candidates) == 1:
        return _finalize_voice(expr, voice_candidates[0], via="leaf", index=index)
    if len(voice_candidates) > 1:
        # Concrete beats container, but ambiguous stays ambiguous — this is
        # the mouth-3 fix: qualified forms now WORK, and the bare form fails
        # loudly listing them, instead of load-time drop-all + silent alloy.
        raise AmbiguousLeaf(expr, name, sorted(voice_candidates))

    group_candidates = _registry.group_leaf_index.get(name, [])
    if len(group_candidates) == 1:
        if index is not None:
            raise BadSelector(expr, f"{name!r} is a group; an index selector needs a resolved voice")
        return _resolve_cast(expr, group_candidates[0])
    if len(group_candidates) > 1:
        raise AmbiguousLeaf(expr, name, sorted(group_candidates))

    bin_candidates = _registry.sample_bin_leaf_index.get(name, [])
    if bin_candidates:
        # Terminal and unambiguous by construction for the common case (a
        # top-level sample bin); if the same leaf names >1 bin, the first
        # canonical id's cure still applies — say so via its own path.
        raise _sample_bin_error(expr, bin_candidates[0])

    if index is None and _is_provider_native(name):
        return VoiceResolution(requested=expr, resolved=name, kind="provider", via="provider-native", profile=None)

    raise Unresolvable(expr, f"no voice, group, or known provider voice named {name!r}", _nearest_matches(name))


def resolve_voice(expr: str) -> VoiceResolution:
    """Resolve a voice expression to a :class:`VoiceResolution`, or raise.

    Total per design.md §3.2 — every branch either returns or raises; there
    is no fall-through to a provider default. Precedence, in order:

    1. path escapes (``/abs``, ``./rel``, ``../rel``, ``~/rel``) — unchanged
    2. a trailing ``[N]`` index suffix on the final segment
    3. ``:`` — reserved (voices/README.md rule 7), no parser meaning; an
       expression containing it is just an opaque name and falls through to
       Unresolvable like any other unknown string
    4. a ``/``-qualified segment walk (voice, group-of-voice, or cast)
    5. a bare name: unique voice leaf, ambiguous leaf, unique group leaf
       (cast), ambiguous group leaf
    6. the provider-native whitelist, checked LAST and explicitly
    7. otherwise: :class:`Unresolvable`, with nearest matches
    """
    _ensure_loaded()
    if not expr:
        raise Unresolvable(expr, "empty voice expression")

    if expr.startswith(("/", "./", "../", "~")):
        selector = expr if expr.startswith("/") else os.path.abspath(os.path.expanduser(expr))
        clip_path = Path(selector)
        sidecar_text = _resolve_transcript(clip_path) if clip_path.exists() else ""
        profile = VoiceProfile(
            name=expr,
            ref_audio=selector,
            ref_text=sidecar_text,
            model=DEFAULT_CLONE_MODEL,
            base_url=DEFAULT_CLONE_BASE_URL,
            description="(absolute path)" if expr.startswith("/") else "(relative path)",
        )
        return VoiceResolution(requested=expr, resolved=selector, kind="clip", via="path-escape", profile=profile)

    body, index = _split_index_suffix(expr)
    if not body:
        raise Unresolvable(expr, "empty voice name")

    if "/" in body:
        return _resolve_segment_walk(expr, body, index)
    return _resolve_bare(expr, body, index)


# ---------------------------------------------------------------------------
# Back-compat wrappers — old "return None/False on failure" contract
# ---------------------------------------------------------------------------

def resolve_voice_expr(expr: str) -> Optional[VoiceProfile]:
    """Resolve a voice expression to a fully-populated ``VoiceProfile``.

    Back-compat wrapper around :func:`resolve_voice`: returns the profile on
    success, ``None`` for anything that isn't a clone/clip voice (including
    every :class:`VoiceResolutionError` — a provider-native name, or a
    genuinely unresolvable one). Callers that need the *loud* contract
    (converse's TTS failover path) should call :func:`resolve_voice`
    directly instead of this function.
    """
    try:
        res = resolve_voice(expr)
    except VoiceResolutionError:
        return None
    if res.kind == "provider":
        return None
    return res.profile


def get_profile(voice_expr: str) -> Optional[VoiceProfile]:
    """Get a voice profile resolved from a voice expression.

    Equivalent to :func:`resolve_voice_expr` — kept under the original
    name for back-compat with existing callers.
    """
    return resolve_voice_expr(voice_expr)


def is_clone_voice(voice_expr: str) -> bool:
    """Check if a voice expression refers to a clone profile.

    Recognises the selector syntax: ``samantha[0]``, ``samantha/angry.wav``,
    and now the group-qualified/cast forms, are all clone voices if they
    resolve to one. Absolute/relative paths always count as clone voices.
    Any :class:`VoiceResolutionError` (unresolvable, ambiguous, undeclared
    cast, ...) means "not a clone voice" here, matching this function's old
    best-effort contract — callers wanting the loud failure use
    :func:`resolve_voice`.
    """
    if not voice_expr:
        return False
    try:
        res = resolve_voice(voice_expr)
    except VoiceResolutionError:
        return False
    return res.kind in ("clone", "clip")


def list_profiles() -> Dict[str, VoiceProfile]:
    """List all available voice profiles, keyed by CANONICAL id (VM-1901).

    Nested voices are now keyed by their full relative path
    (``secretary/lee-holloway``), not their bare leaf — use
    :func:`get_profile` / :func:`resolve_voice` for bare-name lookup, which
    still works for unambiguous leaves via the leaf index.
    """
    _ensure_loaded()
    return _registry.profiles

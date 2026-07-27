"""VM-2072 — the subprocess half of the audio guard.

WHY THIS LAYER EXISTS AT ALL
----------------------------
``sounddevice`` is not the only way this repo makes noise.  ``core.py:610``
shells out to ``paplay``; the DJ feature drives ``mpv``.  The repo's own
``block_dangerous_commands`` fixture blocks neither.  **A green device-layer run
does not by itself prove silence**, so covering the spawn paths is not
belt-and-braces, it is the other half of the claim.

RECORD EVERYTHING, BLOCK ONLY WHAT IS JUDGED AUDIO
--------------------------------------------------
Which programs make sound is a judgement with no API behind it
(``_audio_programs``), and a list is precisely what VM-2072's acceptance
distrusts.  So the list is never allowed to bound what the guard KNOWS:

* **every** spawn is RECORDED, whatever the program;
* only spawns that can actually reach a device are BLOCKED.

An audio player nobody listed then shows up in the census as an unrecognised
spawn instead of vanishing.

TWO TIERS, BECAUSE A FALSE RED COSTS AS MUCH AS A MISS
------------------------------------------------------
``ALWAYS_AUDIO`` programs are blocked on the name alone.  ``CONDITIONAL_AUDIO``
programs are decided on the INVOCATION — ``ffmpeg`` only reaches speakers when
its output muxer is an audio device; ``osascript`` only when the script mentions
say/beep/volume/sound.  This tier is not a nicety: measured on this repo, a
name-only block ABORTED COLLECTION, because ``tests/test_ffmpeg_demo.py`` runs
``ffmpeg -version`` in its module body.  Hits decide the exit status here, so
one phantom fails a whole run and sends somebody hunting a device open that
never happened — on the one task whose entire history is misattributed audio
symptoms.  An allowed conditional spawn is still RECORDED with its decision and
reason.

WHY RUNTIME AND NOT A STATIC SCAN
---------------------------------
Measured: 147 of this repo's 249 spawn call sites build their argv in a
variable — including ``mpv`` (``dj/controller.py:104`` passes a list built at
``:89``).  A static scan would have armed nothing for the exact path named as
the live risk on this machine.

ORDERING
--------
Armed at ``pytest_configure``, i.e. before any fixture runs, so
``block_dangerous_commands``'s captured "original" IS this guard and the chain
holds rather than displacing it.
"""

from __future__ import annotations

import functools
import os
import shlex
import subprocess
import sys
import threading

from . import AudioSubprocessSpawnedInTest, MODE_MUTE, record_hit
from ._audio_programs import ALWAYS_AUDIO, AUDIO_PROGRAMS, CONDITIONAL_AUDIO

#: Every spawn of any kind, for the census (bounded, see _MAX_SPAWNS).
SPAWNS: list = []

#: Cap on the census so a long suite cannot grow the report without bound.
#: Audio hits are NEVER capped — only the ordinary-spawn census is.
_MAX_SPAWNS = 2000

_ORIGINALS: list = []
_PATCHED_PAIRS: list = []
_INSTALLED: list = []
_ARMED: dict = {"targets": {}, "aliases": [], "mode": "block"}

#: Avoids double-recording when a high-level call (subprocess.run) reaches a
#: choke point (fork_exec) that is also guarded.
_IN_FLIGHT = threading.local()


def _basename(token) -> str:
    if isinstance(token, bytes):
        try:
            token = token.decode("utf-8", "replace")
        except Exception:  # pragma: no cover - defensive
            return ""
    if not isinstance(token, str):
        return ""
    return os.path.basename(token)


def _tokens(cmd) -> list:
    """Every token of a command that could name a program.

    A shell string may pipe into a player (``foo | afplay x``), so every token
    is a candidate, not just the first.  Over-approximating here is deliberate:
    a false block costs one loud failure a human reads; a miss costs Mike his
    speakers while he is on a call.
    """
    if cmd is None:
        return []
    if isinstance(cmd, (str, bytes)):
        text = cmd.decode("utf-8", "replace") if isinstance(cmd, bytes) else cmd
        try:
            return shlex.split(text)
        except ValueError:
            return text.split()
    if isinstance(cmd, (list, tuple)):
        out: list = []
        for item in cmd:
            if isinstance(item, (str, bytes)):
                out.append(item.decode("utf-8", "replace")
                           if isinstance(item, bytes) else item)
            elif isinstance(item, os.PathLike):
                out.append(os.fspath(item))
        return out
    if isinstance(cmd, os.PathLike):
        return [os.fspath(cmd)]
    return []


def _audio_match(cmd):
    """Classify a command against the two tiers, carrying the reason either way."""
    tokens = _tokens(cmd)
    for token in tokens:
        base = _basename(token)
        if base in ALWAYS_AUDIO:
            return {
                "program": base,
                "reason": ALWAYS_AUDIO[base],
                "tier": "always",
                "block": True,
                "decision_reason": "the program makes sound whenever it runs",
            }
        if base in CONDITIONAL_AUDIO:
            info = CONDITIONAL_AUDIO[base]
            haystack = " ".join(tokens)
            fired = [t for t in info["triggers"] if t in haystack]
            return {
                "program": base,
                "reason": info["reason"],
                "tier": "conditional",
                "block": bool(fired),
                "triggers_fired": fired,
                "decision_reason": (
                    f"invocation contains {info['trigger_desc']}: {fired}"
                    if fired else
                    f"invocation shows no {info['trigger_desc']} — "
                    f"{info['inert_note']}; ALLOWED and recorded"
                ),
            }
    return None


def _render(cmd) -> str:
    toks = _tokens(cmd)
    text = " ".join(toks) if toks else repr(cmd)
    return text if len(text) <= 300 else text[:300] + "…"


def _census(entry_point: str, cmd, audio) -> None:
    if len(SPAWNS) >= _MAX_SPAWNS:
        return
    SPAWNS.append({
        "entry_point": entry_point,
        "command": _render(cmd),
        "leading_program": next(
            (_basename(t) for t in _tokens(cmd) if _basename(t)), None),
        "audio_capable": bool(audio),
        "blocked": bool(audio and audio["block"]),
    })


def _handle(entry_point: str, cmd) -> bool:
    """Record the spawn; return True if it must be blocked."""
    audio = _audio_match(cmd)
    nested = getattr(_IN_FLIGHT, "depth", 0)
    if not nested or audio:
        _census(entry_point, cmd, audio)
    if not audio:
        return False
    if audio["block"]:
        mode = _ARMED["mode"]
        record_hit(
            "subprocess", entry_point,
            "muted" if mode == MODE_MUTE else "blocked",
            command=_render(cmd),
            program=audio["program"],
            audio_reason=audio["reason"],
            tier=audio["tier"],
            decision_reason=audio["decision_reason"],
        )
        return mode != MODE_MUTE
    # Audio-capable but inert invocation: allowed, and recorded exactly as
    # loudly, so a wrong judgement shows up instead of passing in silence.
    record_hit(
        "subprocess", entry_point, "allowed",
        command=_render(cmd),
        program=audio["program"],
        audio_reason=audio["reason"],
        tier=audio["tier"],
        decision_reason=audio["decision_reason"],
    )
    return False


def _raise(entry_point: str, cmd) -> None:
    audio = _audio_match(cmd) or {}
    raise AudioSubprocessSpawnedInTest(
        f"VM-2072: test code tried to spawn {audio.get('program')!r} via "
        f"{entry_point} — {audio.get('reason')}. "
        f"({audio.get('decision_reason')}) No process was started; the audio "
        "guard blocked it."
    )


def _guard(entry_point: str, original, cmd_index: int = 0,
           cmd_kwargs=("args", "cmd")):
    @functools.wraps(original)
    def guarded(*args, **kwargs):
        cmd = None
        if len(args) > cmd_index:
            cmd = args[cmd_index]
        else:
            for key in cmd_kwargs:
                if key in kwargs:
                    cmd = kwargs[key]
                    break
        if _handle(entry_point, cmd):
            _raise(entry_point, cmd)
        nested = getattr(_IN_FLIGHT, "depth", 0)
        _IN_FLIGHT.depth = nested + 1
        try:
            return original(*args, **kwargs)
        finally:
            _IN_FLIGHT.depth = nested

    guarded.__vm2072_audio_guard__ = entry_point
    return guarded


def _guard_popen(original_popen):
    """``subprocess.Popen`` must stay a real class.

    Tests subscript it (``Popen[bytes]``) and ``isinstance()`` it, and the repo's
    own ``block_dangerous_commands`` wraps it too.  Subclassing keeps both true
    where a plain function would not.
    """

    class GuardedPopen(original_popen):  # type: ignore[misc,valid-type]
        def __init__(self, args=None, *rest, **kwargs):
            cmd = args if args is not None else kwargs.get("args")
            if _handle("subprocess.Popen", cmd):
                _raise("subprocess.Popen", cmd)
            nested = getattr(_IN_FLIGHT, "depth", 0)
            _IN_FLIGHT.depth = nested + 1
            try:
                super().__init__(args, *rest, **kwargs)
            finally:
                _IN_FLIGHT.depth = nested

    GuardedPopen.__name__ = original_popen.__name__
    GuardedPopen.__qualname__ = original_popen.__qualname__
    GuardedPopen.__vm2072_audio_guard__ = "subprocess.Popen"
    return GuardedPopen


def _patch(owner, name: str, replacement) -> None:
    original = getattr(owner, name, None)
    if original is None:
        return
    _ORIGINALS.append((owner, name, original))
    _INSTALLED.append((owner, name, replacement))
    _PATCHED_PAIRS.append((original, replacement))
    setattr(owner, name, replacement)


def _rebind_aliases() -> list:
    """Rebind existing ``from X import Y`` aliases of everything patched above.

    Not theoretical: CPython's own ``subprocess`` holds
    ``from _posixsubprocess import fork_exec as _fork_exec`` (``subprocess.py:104``),
    and VM-2072's rca-001 watched a caller holding a pre-arm reference execute
    straight past the choke-point guard because of it.  One sweep of
    ``sys.modules`` by object identity: the alias set is discovered, not listed.
    """
    if not _PATCHED_PAIRS:
        return []
    by_id = {id(original): replacement for original, replacement in _PATCHED_PAIRS}
    rebound: list = []
    for modname, module in list(sys.modules.items()):
        if module is None or modname.startswith("tests.audio_guard"):
            continue
        namespace = getattr(module, "__dict__", None)
        if not isinstance(namespace, dict):
            continue
        for attr, value in list(namespace.items()):
            replacement = by_id.get(id(value))
            if replacement is None or value is replacement:
                continue
            try:
                setattr(module, attr, replacement)
            except Exception:  # pragma: no cover - defensive
                continue
            _ORIGINALS.append((module, attr, value))
            _INSTALLED.append((module, attr, replacement))
            rebound.append(f"{modname}.{attr}")
    return rebound


def arm(mode: str = "block") -> dict:
    targets: dict = {}

    _patch(subprocess, "Popen", _guard_popen(subprocess.Popen))
    targets["subprocess.Popen"] = "class"
    for name in ("run", "call", "check_call", "check_output",
                 "getoutput", "getstatusoutput"):
        fn = getattr(subprocess, name, None)
        if fn is None:
            continue
        _patch(subprocess, name, _guard(f"subprocess.{name}", fn))
        targets[f"subprocess.{name}"] = "function"

    for name in ("system", "popen", "execv", "execve", "execvp", "execvpe",
                 "execl", "execle", "execlp", "execlpe",
                 "spawnv", "spawnvp", "spawnl", "spawnlp",
                 "posix_spawn", "posix_spawnp"):
        fn = getattr(os, name, None)
        if fn is None:
            continue
        # spawn* take the mode first, so argv starts at position 1.
        idx = 1 if name.startswith("spawn") else 0
        _patch(os, name, _guard(f"os.{name}", fn, cmd_index=idx,
                                cmd_kwargs=("path", "file", "args")))
        targets[f"os.{name}"] = "function"

    try:
        import asyncio

        for name in ("create_subprocess_exec", "create_subprocess_shell"):
            fn = getattr(asyncio, name, None)
            if fn is None:
                continue
            _patch(asyncio, name, _guard(f"asyncio.{name}", fn))
            targets[f"asyncio.{name}"] = "coroutine function"
    except Exception:  # pragma: no cover - defensive
        pass

    # The CPython choke point under Popen on POSIX: a caller holding a pre-arm
    # reference to Popen still exits through here.
    try:
        import _posixsubprocess

        fn = getattr(_posixsubprocess, "fork_exec", None)
        if fn is not None:
            _patch(_posixsubprocess, "fork_exec",
                   _guard("_posixsubprocess.fork_exec", fn, cmd_index=0))
            targets["_posixsubprocess.fork_exec"] = "choke point"
    except Exception:  # pragma: no cover - defensive
        pass

    aliases = _rebind_aliases()
    _ARMED.update({"targets": targets, "aliases": aliases, "mode": mode,
                   "always_audio": sorted(ALWAYS_AUDIO),
                   "conditional_audio": sorted(CONDITIONAL_AUDIO)})
    return dict(_ARMED)


def verify_armed() -> list:
    missing = []
    for owner, name, replacement in _INSTALLED:
        if getattr(owner, name, None) is replacement:
            continue
        missing.append({
            "owner": getattr(owner, "__name__", repr(owner)),
            "attribute": name,
            "found": type(getattr(owner, name, None)).__name__,
        })
    return missing


def disarm() -> None:
    _INSTALLED.clear()
    while _ORIGINALS:
        owner, name, original = _ORIGINALS.pop()
        setattr(owner, name, original)
    _PATCHED_PAIRS.clear()


def census_summary() -> dict:
    programs: dict = {}
    for spawn in SPAWNS:
        prog = spawn.get("leading_program") or "<unknown>"
        programs[prog] = programs.get(prog, 0) + 1
    return {
        "spawn_count": len(SPAWNS),
        "capped_at": _MAX_SPAWNS,
        "programs": programs,
        "audio_programs_watched": sorted(AUDIO_PROGRAMS),
    }

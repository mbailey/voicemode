"""VM-2072 — the audio guard: the real device is never opened by a test run.

WHAT THIS IS
------------
A pytest-level guard that makes the machine's real audio hardware unreachable
from the test suite.  It exists because a default ``pytest`` run on this repo
opened the microphone and put sound through the speakers a live human was
talking through, for about 24 hours, while three crews worked.

**THE NAMED THING IS THE DEVICE, NOT THE MARKERS.**  ``@pytest.mark.audio`` and
``-m "not audio"`` are the convenience layer; they can be forgotten on the next
test anybody writes.  The layer Mike is actually protected by is this guard,
which arms at ``pytest_configure`` — before a single test module is imported —
and requires nobody to remember anything.

THE TWO LAYERS OF THE GUARD ITSELF
----------------------------------
* ``sounddevice_layer`` — the PortAudio path.  Guards every device-touching
  entry point of the *installed* sounddevice (derived at arm time, never typed)
  plus a backstop on the ``_lib`` CFFI handle, which is the hardware boundary
  itself.
* ``subprocess_layer`` — the other way this repo makes noise: shelling out to
  an audio player (``paplay`` at ``core.py:610``, ``mpv`` from the DJ feature,
  ``afplay``, ``say``, ...).  ``sounddevice`` being green does not by itself
  prove silence, so this layer is not optional.

THREE MODES
-----------
``block`` (default)
    Record the crossing and RAISE.  Nothing reaches the device.
``mute``
    Selected automatically for an opt-in ``-m audio`` run.  Record the crossing
    and return an inert stand-in.  Nothing reaches the device *here either* —
    "device-safe by construction", not by a null sink that could be
    misconfigured.  The opt-in path is a path for tests that WANT to exercise
    audio code, not a door onto Mike's speakers.
``off``
    The explicit, loud escape hatch (``VOICEMODE_TEST_AUDIO_GUARD=off``) for
    somebody who genuinely needs a real device.  It announces itself on stderr
    at arm time, in the terminal summary and in every JSON report, because a
    guard that can be silently absent is a dead guard.

WHY EXIT STATUS COMES FROM THE HIT RECORD, NOT FROM PYTEST
----------------------------------------------------------
Measured on this repo (VM-2072 repro-001): the code under test SWALLOWED the
guard's exception and the run still reported "10 passed".  A blocked call that
nobody notices is the same defect as an unblocked one, one step later.  So the
recorded hits — not the test outcomes — decide the exit status
(``failing_hits()``), and a hit recorded after its test finished, on a thread
that outlived it, still reaches the report.

WHO THE DIAGNOSTICS ARE FOR
---------------------------
The person running the suite, and ultimately Mike — not the author of this
file.  Hence: a summary line on EVERY run (so "clean" is distinguishable from
"never armed"), non-coverage printed rather than implied, and any window in
which a guard was lifted reported as an event instead of passing in silence.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import os
import threading
import traceback

__all__ = [
    "MODE_BLOCK",
    "MODE_MUTE",
    "MODE_OFF",
    "NON_COVERAGE",
    "AudioDeviceTouchedInTest",
    "AudioSubprocessSpawnedInTest",
    "EVENTS",
    "HITS",
    "STATE",
    "current_mode",
    "expect_blocked",
    "failing_hits",
    "note",
    "record_hit",
    "set_context",
]

MODE_BLOCK = "block"
MODE_MUTE = "mute"
MODE_OFF = "off"
MODES = (MODE_BLOCK, MODE_MUTE, MODE_OFF)

#: WHAT THIS GUARD DOES NOT COVER — printed in the terminal summary of EVERY
#: run and carried in EVERY JSON report.
#:
#: Reported non-coverage is acceptable; SILENT non-coverage is a dead guard.
#: The distinction is load-bearing here because the guard's verdict line is the
#: only thing most people will read, and a verdict that claims more than the
#: instrument checked is the same defect this whole task exists to close — an
#: instrument that is confidently quiet about something it never looked at.
#:
#: The child-process entry was added by fix-001's peer review, which
#: demonstrated a child ``python -c "import sounddevice; sd.query_devices()"``
#: enumerating ten real devices while this guard printed
#: "GREEN — nothing reached the real audio device".  The spawn WAS recorded;
#: what the child then did was never visible.  See
#: ``evidence/fix-001-review/`` in the task.
NON_COVERAGE: list = [
    {
        "area": "child processes",
        "detail": "the guard lives in THIS interpreter. A spawned child runs "
                  "outside it: every spawn is recorded and judged-audio "
                  "programs are blocked, but a child that opens the device "
                  "ITSELF (e.g. python -c 'import sounddevice') is not "
                  "intercepted and does not appear in the hit record",
        "mediated_by": [
            "every spawn is recorded in the census, so an unrecognised child "
            "is visible rather than absent",
            "VM-2072 rca-001 measured import of all 131 voice_mode modules: "
            "0 sounddevice crossings, so today's `python -m voice_mode` "
            "children touch no audio at import",
        ],
    },
    {
        "area": "tool-use soundfonts",
        "detail": "VOICEMODE_SOUNDFONTS_ENABLED (config.py, defaults TRUE) "
                  "fires on AGENT TOOL CALLS, not on test runs — so no "
                  "test-isolation guard can address it. If this machine still "
                  "makes noise after a green run, this is why; it is not the "
                  "fix having failed",
        "mediated_by": [
            "the guard sets VOICEMODE_SOUNDFONTS_ENABLED=false and "
            "VOICEMODE_AUDIO_FEEDBACK=false for the test process (and hence "
            "its children), so no TEST run emits them",
        ],
    },
    {
        "area": f"{'VOICEMODE_TEST_AUDIO_GUARD'}=off runs",
        "detail": "the deliberate escape hatch: the real device IS reachable. "
                  "Announced on stderr at arm time, in the run header and in "
                  "the summary",
        "mediated_by": ["it announces itself loudly, three times"],
    },
]

#: Env var that overrides the mode.  ``off`` is the deliberate escape hatch.
MODE_ENV = "VOICEMODE_TEST_AUDIO_GUARD"

#: Env var naming a JSON report path.  The terminal summary is always printed;
#: the JSON is for the harness / evidence trail.
REPORT_ENV = "VOICEMODE_AUDIO_GUARD_REPORT"


class AudioDeviceTouchedInTest(Exception):
    """Raised when test code reaches a device-touching sounddevice entry point.

    The exception is the *brake*.  The recorded hit is the *evidence*, and it
    survives code that swallows this exception.
    """


class AudioSubprocessSpawnedInTest(Exception):
    """Raised when test code tries to spawn a program that can make sound."""


#: Every crossing of the audio boundary recorded this session, in order.
HITS: list = []

#: Notable non-crossing events: guards lifted or re-armed, re-arm sweeps, the
#: escape hatch being used.  Printed in the summary and carried in the report —
#: silence about these is exactly the dead-guard failure mode.
EVENTS: list = []

STATE: dict = {
    "mode": None,
    "armed": False,
    "armed_at": None,
    "layers": {},
    "session_finished": False,
}

#: Which test is running, so a crossing can be attributed.  Deliberately
#: initialised to collection time: module-level code in a test file runs at
#: import, before any fixture exists, and one such file lives in this repo
#: (``tests/test_ffmpeg_demo.py`` shells out six times from its module body).
_CONTEXT: dict = {"nodeid": "<collection/import time>", "phase": "collect"}

#: Sanctioned windows: a test that is deliberately provoking the guard (the
#: guard's own regression tests) marks its hits so they do not fail the run.
#: Thread-local by default because a sanctioned window must not accidentally
#: excuse a crossing from unrelated code running in parallel.
_SANCTION = threading.local()
_GLOBAL_SANCTION = {"depth": 0, "label": None}
_LOCK = threading.Lock()


def current_mode() -> str:
    return STATE.get("mode") or MODE_BLOCK


def set_context(nodeid: str | None = None, phase: str | None = None) -> None:
    if nodeid is not None:
        _CONTEXT["nodeid"] = nodeid
    if phase is not None:
        _CONTEXT["phase"] = phase


def context() -> dict:
    return dict(_CONTEXT)


def _short(value, limit: int = 120) -> str:
    try:
        text = repr(value)
    except Exception:  # pragma: no cover - defensive
        text = f"<unreprable {type(value).__name__}>"
    return text if len(text) <= limit else text[:limit] + "…"


def _stack(skip: int = 3) -> list:
    return [
        f"{f.filename}:{f.lineno} {f.name}"
        for f in traceback.extract_stack()[:-skip]
        if "/_pytest/" not in f.filename and "/audio_guard/" not in f.filename
    ][-8:]


def _sanction_state() -> tuple:
    depth = getattr(_SANCTION, "depth", 0)
    label = getattr(_SANCTION, "label", None)
    if depth:
        return depth, label
    with _LOCK:
        return _GLOBAL_SANCTION["depth"], _GLOBAL_SANCTION["label"]


def record_hit(layer: str, entry_point: str, disposition: str, **detail) -> dict:
    """Record one crossing of the audio boundary.

    ``disposition`` is what the guard DID:

    ``blocked``
        raised; this is the disposition that fails the run.
    ``muted``
        inert stand-in returned on the opt-in path — only possible for an
        in-process call.
    ``refused``
        the opt-in path met something that CANNOT be muted (a process spawn:
        once exec'd it owns the speakers and this guard is not inside it), so
        it was stopped instead of pretended away.  Loud, but it does not fail
        the run — using the opt-in path as designed is not a defect.
    ``allowed``
        audio-capable but the invocation cannot reach a device — recorded
        loudly rather than dropped, so a wrong judgement is visible instead of
        silent.
    """
    depth, label = _sanction_state()
    thread = threading.current_thread()
    hit = {
        "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "layer": layer,
        "entry_point": entry_point,
        "disposition": disposition,
        "sanctioned": bool(depth),
        "sanction_label": label,
        "nodeid": _CONTEXT["nodeid"],
        "phase": _CONTEXT["phase"],
        "thread": thread.name,
        "main_thread": thread is threading.main_thread(),
        "after_session_finish": bool(STATE.get("session_finished")),
        "mode": current_mode(),
        "caller_stack_tail": _stack(),
    }
    hit.update(detail)
    with _LOCK:
        HITS.append(hit)
    return hit


def note(event: str, **fields) -> dict:
    """Record a notable event (guard lifted, re-armed, escape hatch used)."""
    record = {
        "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "event": event,
        "nodeid": _CONTEXT["nodeid"],
        "phase": _CONTEXT["phase"],
    }
    record.update(fields)
    with _LOCK:
        EVENTS.append(record)
    return record


def failing_hits() -> list:
    """The hits that must fail the run.

    A crossing fails the run when the guard had to BLOCK it and nobody
    sanctioned it.  ``muted`` crossings on the opt-in path do not fail — they
    are what that path is for — and neither do the guard's own deliberate
    provocations, which are labelled.
    """
    return [
        hit for hit in HITS
        if hit["disposition"] == "blocked" and not hit["sanctioned"]
    ]


@contextlib.contextmanager
def expect_blocked(match: str | None = None, label: str = "", any_thread: bool = False):
    """Provoke the guard on purpose, and assert it fired.

    For the guard's OWN tests, which have to make real calls at real entry
    points — a guard proven only against a fixture is not proven (POLICY 4c).
    Hits recorded inside the window are labelled and excluded from the exit
    status, but they are still recorded and still printed.

    ``any_thread=True`` widens the window to every thread, for the
    post-teardown/worker-thread demonstrations where the crossing deliberately
    happens somewhere else.  Narrow (thread-local) is the default so a
    sanctioned window in one test cannot excuse an unrelated crossing running
    beside it.
    """
    if any_thread:
        with _LOCK:
            _GLOBAL_SANCTION["depth"] += 1
            _GLOBAL_SANCTION["label"] = label or match or "expect_blocked"
    else:
        _SANCTION.depth = getattr(_SANCTION, "depth", 0) + 1
        _SANCTION.label = label or match or "expect_blocked"
    before = len(HITS)
    try:
        yield
    finally:
        if any_thread:
            with _LOCK:
                _GLOBAL_SANCTION["depth"] -= 1
                if _GLOBAL_SANCTION["depth"] == 0:
                    _GLOBAL_SANCTION["label"] = None
        else:
            _SANCTION.depth -= 1
    new = HITS[before:]
    if match is not None:
        new = [h for h in new if match in h["entry_point"]]
    if not new:
        raise AssertionError(
            "audio_guard.expect_blocked: the guard did NOT fire"
            + (f" for {match!r}" if match else "")
            + ". Either the call reached the real device, or it never happened. "
            "Both are failures of this drill."
        )


def report_payload(extra: dict | None = None) -> dict:
    """The machine-readable receipt for a run."""
    failing = failing_hits()
    payload = {
        "task": "VM-2072",
        "instrument": "tests/audio_guard",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "mode": current_mode(),
        "armed": STATE.get("armed"),
        "armed_at": STATE.get("armed_at"),
        "env": {
            key: os.environ.get(key)
            for key in ("VOICEMODE_AUDIO_FEEDBACK", "VOICEMODE_SOUNDFONTS_ENABLED",
                        MODE_ENV)
        },
        "layers": STATE.get("layers", {}),
        # In EVERY report, not only the ones somebody remembered to annotate:
        # a verdict is only as good as the boundary it was measured inside.
        "non_coverage": NON_COVERAGE,
        "verdict_scope": "this pytest process and every thread in it; NOT the "
                         "inside of a child process (see non_coverage)",
        "verdict": "RED" if failing else "GREEN",
        "hit_count": len(HITS),
        "failing_hit_count": len(failing),
        "hits": HITS,
        "events": EVENTS,
    }
    if extra:
        payload.update(extra)
    return payload


def reset_for_tests() -> None:
    """Clear recorded state.  For the guard's own unit tests only."""
    with _LOCK:
        HITS.clear()
        EVENTS.clear()

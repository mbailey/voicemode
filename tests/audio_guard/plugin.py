"""VM-2072 — the pytest wiring for the audio guard.

WHERE IT INSTALLS, AND WHY IT IS NOT AN AUTOUSE FIXTURE
-------------------------------------------------------
``pytest_configure``, from ``tests/conftest.py`` — before a single test module
is imported.  A per-test autouse fixture would not be in the room for
module-level code, and this repo HAS such code: ``tests/test_ffmpeg_demo.py``
is a demo script whose module body pytest executes at collection time (six
subprocess spawns).  Had one of those been ``afplay``, a fixture-based guard
would have missed it entirely — and nobody can put ``@pytest.mark.audio`` on a
module body, which is the marker layer's decay case found by measurement rather
than argument.

WHAT THE PER-TEST FIXTURE IS STILL FOR
--------------------------------------
Not arming — checking.  At every teardown it verifies the guards are still
installed and re-arms any that went missing, so a window opened by
``mock.patch('sounddevice.wait')`` or ``importlib.reload(sounddevice)`` is at
most one test long and is RECORDED either way.

THREADS AND TEARDOWN
--------------------
The guard is scoped to DEVICE RISK, not to test duration.  The observed device
open on this repo happened on a ``ThreadPoolExecutor`` thread, which can outlive
the test that spawned it; a naive fixture-scoped guard would have restored the
real functions before the call landed.  So the guard arms for the whole session
and is deliberately NOT disarmed at ``pytest_unconfigure`` — a late crossing
from a straggler thread is still blocked, still recorded, and (if it lands after
the summary) still shouted about by the ``atexit`` handler.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import sys

import pytest

from . import (
    EVENTS,
    HITS,
    MODE_BLOCK,
    MODE_ENV,
    MODE_MUTE,
    MODE_OFF,
    MODES,
    REPORT_ENV,
    STATE,
    failing_hits,
    note,
    report_payload,
    set_context,
)
from . import sounddevice_layer, subprocess_layer

#: Env vars that silence voicemode's chimes and tool-use soundfonts.  Both
#: default to TRUE in config.py, so an un-exported shell is the harmful
#: configuration.  Setting them here (before voice_mode is imported) makes the
#: safe value the default for every test run, rather than something each agent
#: has to remember to export.
_MITIGATION_ENV = {
    "VOICEMODE_AUDIO_FEEDBACK": "false",
    "VOICEMODE_SOUNDFONTS_ENABLED": "false",
}

_BANNER = "=" * 72


def _resolve_mode(config) -> tuple:
    """Pick the mode, and say why — the reason is printed in the summary."""
    override = os.environ.get(MODE_ENV)
    if override:
        mode = override.strip().lower()
        if mode not in MODES:
            raise pytest.UsageError(
                f"{MODE_ENV}={override!r}: expected one of {', '.join(MODES)}."
            )
        return mode, f"{MODE_ENV}={mode} (explicit override)"

    markexpr = getattr(config.option, "markexpr", "") or ""
    opts_in = bool(re.search(r"\baudio\b", markexpr)) and not re.search(
        r"\bnot\s+audio\b", markexpr
    )
    if opts_in:
        return MODE_MUTE, f"opt-in run selected by -m {markexpr!r}: muted, not live"
    return MODE_BLOCK, "default run: the device is unreachable"


def install(config) -> None:
    """Arm the guard.  Called from ``tests/conftest.py``'s ``pytest_configure``."""
    if STATE.get("armed"):
        return

    applied_env = {}
    for key, value in _MITIGATION_ENV.items():
        if key not in os.environ:
            os.environ[key] = value
            applied_env[key] = value

    mode, reason = _resolve_mode(config)
    STATE["mode"] = mode
    STATE["mode_reason"] = reason
    STATE["mitigation_env_applied"] = applied_env

    if mode == MODE_OFF:
        # The escape hatch announces itself.  A guard that can be absent
        # silently is indistinguishable from a guard that never worked.
        message = (
            f"\n{_BANNER}\n"
            "⚠️  VM-2072 AUDIO GUARD IS OFF — this run CAN open the real audio\n"
            "    device and put sound through the speakers of whoever is at this\n"
            f"    machine. Requested by {MODE_ENV}=off.\n"
            f"{_BANNER}\n"
        )
        print(message, file=sys.stderr, flush=True)
        note("guard-disabled", detail=reason)
        STATE["armed"] = False
        STATE["layers"] = {}
    else:
        STATE["layers"] = {
            "sounddevice": sounddevice_layer.arm(mode),
            "subprocess": subprocess_layer.arm(mode),
        }
        STATE["armed"] = True
        STATE["armed_at"] = STATE["layers"]["sounddevice"].get("armed_at")

    config.pluginmanager.register(_Reporter(config), "vm2072_audio_guard_reporter")
    atexit.register(_report_late_hits)


class _Reporter:
    def __init__(self, config):
        self.config = config

    # -- attribution -------------------------------------------------------
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        set_context(nodeid=item.nodeid)
        yield
        # Deliberately names the test just finished: a crossing arriving here
        # came from something that outlived it, and that attribution is the
        # useful half of the record.
        set_context(nodeid=f"<after {item.nodeid}>", phase="post-test")

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_setup(self, item):
        set_context(phase="setup")
        yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        set_context(phase="call")
        yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_teardown(self, item, nextitem):
        set_context(phase="teardown")
        yield
        # After the yield: fixtures have finalised, so anything still missing
        # was not a fixture's temporary patch — it is a real hole.
        self._verify_still_armed(item.nodeid)

    def _verify_still_armed(self, nodeid: str) -> None:
        if not STATE.get("armed"):
            return
        for layer, module in (("sounddevice", sounddevice_layer),
                              ("subprocess", subprocess_layer)):
            missing = module.verify_armed()
            if not missing:
                continue
            note(
                "guard-missing-at-teardown",
                layer=layer,
                nodeid=nodeid,
                missing=missing,
                detail="a guard was not installed at the end of this test; "
                       "the device was unguarded at that entry point for part "
                       "of the test. Re-arming now.",
            )
            restored = module.rearm(missing) if hasattr(module, "rearm") else 0
            note("guard-rearmed", layer=layer, nodeid=nodeid, restored=restored)

    # -- reporting ---------------------------------------------------------
    def pytest_report_header(self, config):
        if not STATE.get("armed"):
            return ("VM-2072 audio guard: ⚠️  NOT ARMED — "
                    f"{STATE.get('mode_reason')}")
        sd_layer = STATE["layers"]["sounddevice"]
        proc = STATE["layers"]["subprocess"]
        return (
            f"VM-2072 audio guard: ARMED mode={STATE['mode']} "
            f"({STATE['mode_reason']}); "
            f"sounddevice {sd_layer['guard_count']} guards over "
            f"{len(sd_layer['covered'])} derived entry points "
            f"(v{sd_layer['sounddevice_version']}), backstop="
            f"{sd_layer['backstop_installed']}; "
            f"{len(proc['targets'])} spawn entry points"
        )

    def pytest_terminal_summary(self, terminalreporter):
        write = terminalreporter.write_line
        write("")
        write(_BANNER)
        if not STATE.get("armed"):
            write("VM-2072 AUDIO GUARD: ⚠️  NOT ARMED FOR THIS RUN")
            write(f"  reason: {STATE.get('mode_reason')}")
            write("  This run was free to open the real audio device.")
            write(_BANNER)
            self._maybe_write_report(write)
            return

        sd_layer = STATE["layers"]["sounddevice"]
        proc = STATE["layers"]["subprocess"]
        write(f"VM-2072 AUDIO GUARD — mode={STATE['mode']} ({STATE['mode_reason']})")
        write(
            f"  sounddevice: {sd_layer['guard_count']} guards on "
            f"{len(sd_layer['covered'])} entry points, DERIVED at arm time from "
            f"sounddevice {sd_layer['sounddevice_version']} "
            f"({sd_layer['device_touching']}/{sd_layer['derived_entry_points']} "
            "public surfaces reach PortAudio)"
        )
        write(
            f"  PortAudio backstop: {'installed' if sd_layer['backstop_installed'] else 'MISSING'}"
            f" — {len(sd_layer['backstop_passthrough'])} symbols deliberately let "
            "through (see the JSON report for each reason)"
        )
        write(
            f"  aliases rebound by identity: {len(sd_layer['rebound_aliases'])} "
            f"sounddevice, {len(proc['aliases'])} subprocess"
        )
        write(
            f"  subprocess: {len(proc['targets'])} spawn entry points armed; "
            f"{len(proc['always_audio'])} always-audio + "
            f"{len(proc['conditional_audio'])} conditional programs watched; "
            f"every spawn recorded ({subprocess_layer.census_summary()['spawn_count']} seen)"
        )
        for name, info in sorted(sd_layer["mediated"].items()):
            write(f"  not guarded (mediated): sounddevice.{name} — every route "
                  f"runs through {', '.join(info['mediated_by'])}")
        if not sd_layer["rebinding_watcher"]:
            write("  ⚠️  rebinding watcher unavailable: a lifted guard would not "
                  "be visible until teardown")

        self._write_events(write)
        self._write_hits(write)
        self._maybe_write_report(write)
        write(_BANNER)

    def _write_events(self, write) -> None:
        if not EVENTS:
            return
        write(f"  events: {len(EVENTS)}")
        for event in EVENTS[:20]:
            detail = event.get("attribute") or event.get("layer") or ""
            write(f"    [{event['event']}] {detail} <- {event['nodeid']}")
        if len(EVENTS) > 20:
            write(f"    … {len(EVENTS) - 20} more (see the JSON report)")

    def _write_hits(self, write) -> None:
        failing = failing_hits()
        by_disposition: dict = {}
        for hit in HITS:
            by_disposition.setdefault(hit["disposition"], []).append(hit)

        for disposition, label in (
            ("muted", "muted on the opt-in path (no device touched)"),
            ("allowed", "audio-capable but inert invocation — ALLOWED, recorded"),
        ):
            hits = by_disposition.get(disposition, [])
            if not hits:
                continue
            write(f"  {len(hits)} {label}:")
            for key, count in sorted(_group(hits).items()):
                write(f"    {key[1]}  ×{count}  <- {key[0]}")

        sanctioned = [h for h in HITS
                      if h["disposition"] == "blocked" and h["sanctioned"]]
        if sanctioned:
            write(f"  {len(sanctioned)} deliberate provocation(s) of the guard "
                  "(the guard's own drills), blocked and excused:")
            for key, count in sorted(_group(sanctioned).items()):
                write(f"    {key[1]}  ×{count}  <- {key[0]}")

        if not failing:
            write("RESULT: GREEN — nothing reached the real audio device.")
            return
        write(f"RESULT: RED — {len(failing)} call(s) reached the audio boundary "
              "and were BLOCKED:")
        for key, count in sorted(_group(failing).items()):
            write(f"    {key[1]}  ×{count}  <- {key[0]}")
        write("  The device was NOT opened. This run fails on the guard's own "
              "hit record, whatever the tests reported.")

    def _maybe_write_report(self, write) -> None:
        path = os.environ.get(REPORT_ENV)
        if not path:
            return
        payload = report_payload({
            "pytest_args": list(self.config.invocation_params.args),
            "subprocess_census": subprocess_layer.census_summary(),
            "spawns": subprocess_layer.SPAWNS,
        })
        with open(path, "w") as fh:
            json.dump(payload, fh, indent=2, default=str)
            fh.write("\n")
        write(f"  report: {path}")

    # -- exit status -------------------------------------------------------
    def pytest_sessionfinish(self, session, exitstatus):
        """The hit record decides the exit status, not the test outcomes.

        Measured on this repo: the code under test swallowed the guard's
        exception and the run still reported "10 passed".  A blocked call that
        the suite forgives is a defect one step later, so it fails the run here.
        """
        STATE["session_finished"] = True
        failing = failing_hits()
        if failing and exitstatus == 0:
            session.exitstatus = 1


def _group(hits) -> dict:
    grouped: dict = {}
    for hit in hits:
        key = (hit["nodeid"], hit["entry_point"])
        grouped[key] = grouped.get(key, 0) + 1
    return grouped


def _report_late_hits() -> None:
    """Shout about a crossing that landed after the summary was printed.

    A straggler thread can cross the audio boundary after pytest has finished
    reporting.  The exit status is already decided by then, so the only honest
    thing left is to make the record impossible to miss — on stderr, where the
    person running the suite is looking.
    """
    late = [hit for hit in HITS if hit.get("after_session_finish")]
    if not late:
        return
    print(f"\n{_BANNER}", file=sys.stderr)
    print(f"⚠️  VM-2072 AUDIO GUARD: {len(late)} audio boundary crossing(s) "
          "arrived AFTER the test session finished — from a thread that "
          "outlived its test. They were blocked; the exit status was already "
          "decided.", file=sys.stderr)
    for hit in late[:10]:
        print(f"    {hit['entry_point']} on thread {hit['thread']} "
              f"<- {hit['nodeid']}", file=sys.stderr)
    print(_BANNER, file=sys.stderr, flush=True)

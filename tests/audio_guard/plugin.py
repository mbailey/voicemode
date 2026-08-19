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
    NON_COVERAGE,
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
    # The invariant is "these two hold their arm-time value for the whole run",
    # not "what I set stays set" -- so verification is against the EFFECTIVE
    # values, which is what a shell that already exported them chose. A test
    # that deletes them mid-run is drift either way.
    STATE["mitigation_env_effective"] = {
        key: os.environ.get(key) for key in _MITIGATION_ENV
    }
    # READ THE REPORT PATH ONCE, HERE, AND KEEP IT.  os.environ belongs to the
    # code under test as much as to us: tests/test_config_multiline.py deleted
    # every VOICEMODE_* variable and did not put them back, so in every
    # full-suite run this guard's JSON receipt was silently never written --
    # the terminal summary printed, nobody noticed, and the machine-readable
    # evidence simply did not exist.  An instrument's own receipt must not
    # depend on what the things it is measuring do to the environment.
    STATE["report_path"] = os.environ.get(REPORT_ENV)

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

    @pytest.hookimpl(hookwrapper=True)
    def pytest_make_collect_report(self, collector):
        """Collection is where a module-level replacement actually happens.

        ``sys.modules['sounddevice'] = MagicMock()`` in a test file's body runs
        when pytest IMPORTS that file — during collection, before any test.
        Checking here is what lets the report NAME THE FILE RESPONSIBLE instead
        of blaming whichever test happened to tear down first (measured: the
        first victim was ``tests/dj/test_chapters.py``, which has nothing to do
        with audio).
        """
        yield
        if STATE.get("armed"):
            self._check_sounddevice_module(
                getattr(collector, "nodeid", None) or repr(collector))

    def _check_sounddevice_module(self, source: str) -> None:
        """Answer a WHOLESALE REPLACEMENT of the sounddevice module.

        Three outcomes, and the choice between them is the whole point:

        * **still ours** — nothing to do (and if a previously reported
          replacement has gone away, say so and resume normal verification).
        * **a real sounddevice** — adopt it: derive and arm again.  This is
          coverable, so it gets covered rather than reported as a hole.
        * **anything else** (a ``MagicMock``, a stub, or removed outright) —
          the guard CANNOT cover it: it has no ``_lib`` to back-stop and no
          source to derive from.  Report it ONCE, loudly, as a named
          non-coverage condition, and stop verifying the sounddevice layer.

        ONCE is load-bearing.  The previous behaviour re-derived on every
        teardown and raised out of the hookwrapper each time: 2116 errors and
        4234 events in one run.  Reported non-coverage is acceptable; a guard
        that shouts 2116 times is removed by the first person in a hurry, which
        leaves no guard at all.
        """
        replacement = sounddevice_layer.module_replaced()
        active = STATE.get("sounddevice_module_replaced")
        if replacement is None:
            if active:
                STATE["sounddevice_module_replaced"] = None
                note("sounddevice-module-restored",
                     replaced_by=active["by"],
                     detail="the sounddevice module we armed is back in "
                            "sys.modules; the guards on it were never removed, "
                            "so coverage resumes here")
            return
        if active:
            return  # reported once. Never once per test.
        if replacement["adoptable"] and sounddevice_layer.adopt_replacement():
            note("sounddevice-module-adopted",
                 by=source,
                 detail="sys.modules['sounddevice'] was replaced with a REAL "
                        "sounddevice module; guards were derived and installed "
                        "on it, so coverage continues",
                 **replacement)
            return

        record = dict(replacement, by=source)
        STATE["sounddevice_module_replaced"] = record
        note("sounddevice-module-replaced", **record)
        NON_COVERAGE.append({
            "area": "sounddevice replaced in sys.modules",
            "detail": (
                f"{source} put a {replacement['replaced_with']} in "
                "sys.modules['sounddevice'], so from that point on any code "
                "importing sounddevice gets that object and NOT the guarded "
                "module. The guard cannot see through it and did not try: "
                "reported here rather than silently assumed covered"
            ),
            "mediated_by": [
                "the guards this session installed are still on the real "
                "sounddevice module object, so any caller holding it (anything "
                "that imported sounddevice before the replacement) is still "
                "guarded",
                "the replacement is reported in the run header area, in this "
                "summary, in the JSON report and on stderr",
            ],
        })
        print(
            f"\n{_BANNER}\n"
            "⚠️  VM-2072 AUDIO GUARD — COVERAGE IS INCOMPLETE FROM HERE ON.\n"
            f"    {source} replaced sys.modules['sounddevice'] with a "
            f"{replacement['replaced_with']}.\n"
            "    Code importing sounddevice after this point gets that object, "
            "not the\n    guarded module, and this guard cannot see through "
            "it.\n"
            "    Fix the file (patch the seam you are testing, not the whole "
            "module) or\n    accept the stated gap.\n"
            f"{_BANNER}\n",
            file=sys.stderr, flush=True,
        )

    @staticmethod
    def _verify_mitigation_env(nodeid: str) -> None:
        """Put back the two variables that keep this machine quiet.

        The guard sets VOICEMODE_AUDIO_FEEDBACK=false and
        VOICEMODE_SOUNDFONTS_ENABLED=false at arm time so nobody has to remember
        to export them.  A test is free to delete them -- and one did, for the
        whole session, as a side effect of testing the config loader.  Anything
        that reads them AFTER that point (a reimport, a subprocess, a reloaded
        config module) gets the harmful default back.

        So they are re-asserted, and the drift is REPORTED ONCE: silently
        restoring would hide a real class of test that leaks environment.
        """
        drifted = {}
        for key, value in (STATE.get("mitigation_env_effective") or {}).items():
            if value is None:
                continue
            if os.environ.get(key) != value:
                drifted[key] = os.environ.get(key)
                os.environ[key] = value
        if drifted and not STATE.get("mitigation_env_drift_reported"):
            STATE["mitigation_env_drift_reported"] = True
            note(
                "mitigation-env-restored",
                nodeid=nodeid,
                drifted=drifted,
                detail="a test removed or changed the audio-mitigation "
                       "environment the guard set at arm time; restored. "
                       "Reported once -- anything reading these variables in "
                       "the window got the harmful default",
            )

    def _verify_still_armed(self, nodeid: str) -> None:
        if not STATE.get("armed"):
            return
        self._verify_mitigation_env(nodeid)
        self._check_sounddevice_module(nodeid)
        for layer, module in (("sounddevice", sounddevice_layer),
                              ("subprocess", subprocess_layer)):
            if layer == "sounddevice" and STATE.get("sounddevice_module_replaced"):
                # Already reported, and there is nothing here to verify: the
                # name no longer resolves to the module we armed.
                continue
            missing = module.verify_armed()
            if not missing and getattr(module, "reloaded", bool)():
                # A reload writes straight into the module __dict__, so nothing
                # observes it as it happens. Ask directly.
                missing = [{"owner": "sounddevice", "attribute": "<module reloaded>",
                            "found": "rebuilt module"}]
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
            self._repair(layer, module, nodeid, missing)

    @staticmethod
    def _repair(layer: str, module, nodeid: str, missing: list) -> None:
        """Re-arm, and report ONLY what actually happened.

        ⚠️ THE GUARD NEVER REPORTS AN ACTION IT DID NOT PERFORM.  This used to
        read ``module.rearm(missing) if hasattr(module, 'rearm') else 0``
        followed unconditionally by ``note("guard-rearmed", restored=0)`` — and
        the subprocess layer had no ``rearm()``, so every one of its windows was
        logged as repaired while nothing was repaired.  That is the dead-guard
        family pointing the other way: not a check that silently fails, but a
        log that manufactures confidence in exactly the record a human consults
        after an incident.  Found by fix-001's peer review.

        So there are now three distinct outcomes and three distinct events:
        the repair happened, the repair was attempted and restored nothing, or
        the layer cannot perform one at all.
        """
        repair = getattr(module, "rearm", None)
        if repair is None:  # pragma: no cover - no such layer today
            note(
                "guard-not-rearmable",
                layer=layer,
                nodeid=nodeid,
                missing=missing,
                detail="this layer cannot re-install its guards; the window "
                       "stays open. Recorded as unrepaired rather than claimed "
                       "repaired.",
            )
            return
        restored = repair(missing)
        if restored == -1:
            # The sounddevice layer's answer to a reload: the module's classes
            # were rebuilt, so it re-derives and re-arms wholesale rather than
            # counting attributes.
            note("guard-rearmed", layer=layer, nodeid=nodeid, restored="all",
                 detail="the layer was re-derived and armed again from scratch")
        elif restored:
            note("guard-rearmed", layer=layer, nodeid=nodeid, restored=restored)
        else:
            note(
                "guard-rearm-failed",
                layer=layer,
                nodeid=nodeid,
                missing=missing,
                detail="re-arming restored NOTHING — these entry points are "
                       "still unguarded and this run's coverage is incomplete "
                       "from here on.",
            )

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

        self._write_non_coverage(write)
        self._write_events(write)
        self._write_hits(write)
        self._maybe_write_report(write)
        write(_BANNER)

    def _write_non_coverage(self, write) -> None:
        """State the boundary the verdict was measured inside — every run.

        The verdict line below is the only thing most people read, so it must
        not claim more than the instrument looked at.  A child process is the
        sharp case: the guard records the spawn and blocks judged-audio
        programs, but it does not live inside the child, so a child that opens
        the device itself never reaches the hit record.
        """
        census = subprocess_layer.census_summary()
        write(f"  not covered — stated, never silent ({len(NON_COVERAGE)}):")
        for item in NON_COVERAGE:
            extra = ""
            if item["area"] == "child processes":
                extra = (f" [{census['spawn_count']} spawned this run: "
                         f"{census['programs'] or 'none'}]")
            write(f"    • {item['area']}: {item['detail']}{extra}")

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
            ("refused", "REFUSED on the opt-in path — a process cannot be "
                        "muted, only not started (use "
                        "VOICEMODE_TEST_AUDIO_GUARD=off for a live spawn)"),
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

        replaced = STATE.get("sounddevice_module_replaced")
        if replaced:
            write("")
            write("⚠️  sounddevice was REPLACED in sys.modules by "
                  f"{replaced['by']} (a {replaced['replaced_with']}). "
                  "Everything importing sounddevice after that point bypassed "
                  "this guard; the verdict below is scoped accordingly.")

        if not failing:
            if replaced:
                write("RESULT: GREEN, BUT COVERAGE WAS INCOMPLETE — nothing "
                      "this guard could still see reached the real audio "
                      "device. It stopped being able to see the sounddevice "
                      f"path at {replaced['by']}.")
                return
            # Scoped deliberately. "Nothing reached the device" is a bigger
            # claim than this instrument can make: it sees this process and
            # every thread in it, and it sees that a child was spawned, but
            # not what the child did once it was running.
            write("RESULT: GREEN — nothing IN THIS PROCESS reached the real "
                  "audio device (see 'not covered' above for the boundary).")
            return
        write(f"RESULT: RED — {len(failing)} call(s) reached the audio boundary "
              "and were BLOCKED:")
        for key, count in sorted(_group(failing).items()):
            write(f"    {key[1]}  ×{count}  <- {key[0]}")
        write("  The device was NOT opened. This run fails on the guard's own "
              "hit record, whatever the tests reported.")

    def _maybe_write_report(self, write) -> None:
        path = STATE.get("report_path") or os.environ.get(REPORT_ENV)
        if not path:
            return
        payload = report_payload({
            "sounddevice_module_replaced": STATE.get("sounddevice_module_replaced"),
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

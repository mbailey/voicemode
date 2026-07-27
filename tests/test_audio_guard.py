"""VM-2072 — the audio guard, drilled in BOTH directions.

A guard nobody has seen fail is not known to work, and a guard nobody has seen
*decline* to fire is not known to be safe either.  A false RED costs as much as
a miss here: hits decide the exit status, so one phantom fails a whole suite and
sends somebody hunting a device open that never happened — on the one repo whose
audio symptoms have already been misattributed once.

So every drill below is one of two shapes:

* **fires when it should** — a real call at a real entry point, blocked;
* **does not fire when it should not** — an inert call that must pass through
  untouched and unrecorded.

These are deliberate provocations, so they run inside ``expect_blocked()``,
which labels their hits and keeps them out of the exit status.  It also asserts
the guard actually fired: a drill that provokes nothing fails.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest
import sounddevice as sd

from tests import audio_guard
from tests.audio_guard import (
    AudioDeviceTouchedInTest,
    AudioSubprocessSpawnedInTest,
    expect_blocked,
    subprocess_layer,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Silent audio.  If every layer of the guard were broken at once this would
#: still make no sound — the drills are written so that failure is quiet, not
#: painful for whoever is at the machine.
SILENCE = np.zeros((1024, 1), dtype=np.float32)


class TestGuardIsArmed:
    """A clean run must be distinguishable from a run where nothing armed."""

    def test_guard_is_armed_in_a_default_run(self):
        assert audio_guard.STATE["armed"] is True, (
            "the audio guard did not arm — a green run means nothing"
        )
        assert audio_guard.current_mode() == audio_guard.MODE_BLOCK

    def test_covered_set_is_derived_not_typed(self):
        layer = audio_guard.STATE["layers"]["sounddevice"]
        assert layer["guard_count"] > 20
        assert layer["sounddevice_version"] == sd.__version__
        assert layer["backstop_installed"] is True


class TestSounddeviceLayerFires:
    def test_play_is_blocked(self):
        with expect_blocked("play", label="drill: sd.play"):
            with pytest.raises(AudioDeviceTouchedInTest):
                sd.play(SILENCE, samplerate=44100)

    def test_lazy_in_function_import_is_blocked(self):
        """The shape used at config.py:1423 and core.py:491/502/833."""
        def records():
            import sounddevice as lazily_imported

            return lazily_imported.rec(1024, samplerate=16000, channels=1)

        with expect_blocked("rec", label="drill: lazy import"):
            with pytest.raises(AudioDeviceTouchedInTest):
                records()

    def test_from_import_alias_is_blocked(self):
        """``from sounddevice import play`` binds the object, not the module."""
        from sounddevice import play as aliased

        with expect_blocked("play", label="drill: from-import alias"):
            with pytest.raises(AudioDeviceTouchedInTest):
                aliased(SILENCE, samplerate=44100)

    def test_stream_subclass_nobody_enumerated_is_blocked(self):
        """The not-a-whitelist property, demonstrated rather than argued.

        This class did not exist when the guard armed and appears in no
        enumeration anywhere.  It is caught because every stream in sounddevice
        constructs through ``_StreamBase``.
        """
        class StreamNobodyHasEverSeen(sd._StreamBase):
            pass

        with expect_blocked("_StreamBase.__init__", label="drill: novel subclass"):
            with pytest.raises(AudioDeviceTouchedInTest):
                StreamNobodyHasEverSeen(kind="output", samplerate=44100, channels=1)

    def test_property_is_guarded_as_a_property(self):
        """Patching a property with a bare function would silently disarm it.

        ``Stream.active`` is a property: replacing it with a plain function
        turns a guarded read into an unguarded attribute lookup and the guard
        never fires — silently, which is this task's whole defect family.
        """
        static = inspect.getattr_static(sd.Stream, "active")
        assert isinstance(static, property), "the guard replaced a property with a function"

        # object.__new__ skips the (guarded) __init__, so the property getter
        # can be reached without opening anything first.
        uninitialised = object.__new__(sd.Stream)
        with expect_blocked("Stream.active", label="drill: property"):
            with pytest.raises(AudioDeviceTouchedInTest):
                uninitialised.active

    def test_hit_is_recorded_even_when_the_caller_swallows_the_exception(self):
        """Measured on this repo: the code under test caught the guard and the
        run still said "10 passed".  The record is what survives that."""
        before = len(audio_guard.HITS)
        with expect_blocked("query_devices", label="drill: swallowed"):
            try:
                sd.query_devices()
            except Exception:  # exactly what dependencies.py:90 does
                pass
        assert len(audio_guard.HITS) > before


class TestPortAudioBackstop:
    """Layer 3: the hardware boundary itself, for anything the derivation missed."""

    def test_direct_lib_call_is_caught(self):
        with expect_blocked("_lib.Pa_GetDeviceCount", label="drill: backstop"):
            with pytest.raises(AudioDeviceTouchedInTest):
                sd._lib.Pa_GetDeviceCount()

    def test_inert_symbols_pass_through_untouched(self):
        """False-positive drill.  Version and error-text symbols touch nothing;
        blocking ``Pa_GetErrorText`` would corrupt ``PortAudioError.__str__``."""
        before = len(audio_guard.HITS)
        version = sd._lib.Pa_GetVersion()
        assert isinstance(version, int)
        assert len(audio_guard.HITS) == before, "the backstop recorded an inert call"

    def test_constants_are_not_calls(self):
        before = len(audio_guard.HITS)
        assert sd._lib.paClipOff is not None
        assert len(audio_guard.HITS) == before


class TestNoFalsePositives:
    def test_portaudio_error_construction_is_not_a_hit(self):
        """Live site: converse.py:1552 raises ``sd.PortAudioError`` on the
        device-disconnected path.  Recording that as a device touch would fail
        runs for an error handler doing its job."""
        before = len(audio_guard.HITS)
        error = sd.PortAudioError("device disconnected")
        assert isinstance(error, Exception)
        # Rendering it must not fire either: PortAudioError.__str__ only reaches
        # the device on its three-argument branch, and AST reachability cannot
        # see that. The derivation leaves it MEDIATED and says so in the report
        # rather than guarding it and inventing a phantom hit here.
        assert "device disconnected" in str(error)
        assert len(audio_guard.HITS) == before

    def test_ordinary_subprocess_is_not_recorded_as_a_crossing(self):
        before = len(audio_guard.HITS)
        subprocess.run([sys.executable, "-c", "pass"], check=True)
        assert len(audio_guard.HITS) == before

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
    def test_inert_ffmpeg_invocation_is_allowed_and_recorded(self):
        """``ffmpeg -version`` cannot make a sound, and blocking it once aborted
        collection of this very suite.  It is ALLOWED — and still recorded, so a
        wrong judgement is visible instead of silent."""
        before = len(audio_guard.HITS)
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        new = audio_guard.HITS[before:]
        assert new, "an audio-capable spawn was allowed WITHOUT being recorded"
        assert all(hit["disposition"] == "allowed" for hit in new)
        assert not [hit for hit in new if hit["disposition"] == "blocked"]


class TestSubprocessLayerFires:
    def test_audio_player_is_blocked(self):
        with expect_blocked("subprocess.run", label="drill: afplay"):
            with pytest.raises(AudioSubprocessSpawnedInTest):
                subprocess.run(["afplay", "/System/Library/Sounds/Ping.aiff"])

    def test_argv_built_at_runtime_is_still_caught(self):
        """The DJ path builds its ``mpv`` argv in a variable
        (``dj/controller.py:104`` from a list built at ``:89``), so a static
        scan would arm nothing for it.  Interception is at runtime."""
        player = "mpv"
        command = [player, "--no-video", "/tmp/track.mp3"]
        with expect_blocked("subprocess.Popen", label="drill: mpv"):
            with pytest.raises(AudioSubprocessSpawnedInTest):
                subprocess.Popen(command)

    def test_shell_pipeline_into_a_player_is_caught(self):
        with expect_blocked(label="drill: shell pipeline"):
            with pytest.raises(AudioSubprocessSpawnedInTest):
                os.system("cat /tmp/x.wav | paplay")


class TestOneSpawnIsOneEntry:
    """A single spawn crosses three guarded surfaces; it must count once.

    ``subprocess.run`` → ``subprocess.Popen`` → ``_posixsubprocess.fork_exec``
    are all guarded, so one ``ffprobe`` used to appear as three spawns and
    three hits.  The census is what the guard offers as evidence about child
    processes it cannot see INSIDE (see ``NON_COVERAGE``), so it has to count
    processes rather than call frames or the evidence is inflated threefold.
    """

    @pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe not installed")
    def test_one_audio_capable_spawn_records_one_hit(self):
        before = len(audio_guard.HITS)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        new = audio_guard.HITS[before:]
        assert len(new) == 1, [h["entry_point"] for h in new]
        assert new[0]["disposition"] == "allowed"


class TestOptInPathRefusesWhatItCannotMute:
    """⚠️ A PROCESS CANNOT BE MUTED — it can only not be started.

    The mute path originally recorded an audio spawn as *"muted ... no device
    touched"* and then **really ran it**: ``afplay`` under ``pytest -m audio``
    would have played through the speakers of whoever is at this machine while
    the report said the run was quiet.  Found by fix-001's peer review, proven
    with a spawn that reached the exec and died on ENOENT (nothing audible).

    This drill keeps that door shut.  It provokes the mute decision directly
    rather than under ``-m audio``, because the drill must run in the DEFAULT
    suite — a regression test that only runs on the opt-in path would be
    protecting the opt-in path with a test on the opt-in path.
    """

    def test_mute_mode_refuses_an_audio_spawn_instead_of_running_it(self, monkeypatch):
        from tests.audio_guard import subprocess_layer

        monkeypatch.setitem(subprocess_layer._ARMED, "mode", audio_guard.MODE_MUTE)
        before = len(audio_guard.HITS)

        # pw-play is PipeWire: it cannot exist on this Darwin host, so if the
        # guard ever lets this through again the failure is ENOENT rather than
        # a noise. The assertion is that we never get that far.
        with pytest.raises(AudioSubprocessSpawnedInTest) as excinfo:
            subprocess.run(["pw-play", "/tmp/does-not-exist.wav"])

        assert "cannot be muted" in str(excinfo.value)
        new = audio_guard.HITS[before:]
        assert len(new) == 1
        assert new[0]["disposition"] == "refused", (
            "an audio spawn on the opt-in path must be REFUSED — recording it "
            "as 'muted' and running it anyway is how this bug read as quiet"
        )

    def test_a_refusal_does_not_fail_the_run(self):
        """Using the opt-in path as designed is not a defect."""
        refused = [h for h in audio_guard.HITS if h["disposition"] == "refused"]
        assert refused, "the refusal drill above did not record anything"
        assert not [h for h in audio_guard.failing_hits()
                    if h["disposition"] == "refused"]


class TestNonCoverageIsStatedNotSilent:
    """Reported non-coverage is acceptable; silent non-coverage is a dead guard.

    The sharp case is a CHILD PROCESS.  The guard records every spawn and
    blocks judged-audio programs, but it does not live inside the child: a
    child that opens the device itself never reaches the hit record.  Peer
    review demonstrated a child ``python -c "import sounddevice;
    sd.query_devices()"`` enumerating ten real devices while the summary
    printed *"GREEN — nothing reached the real audio device"*.

    The gap is narrow and is not closable from here — but a verdict that
    claims more than the instrument looked at is this task's own defect shape,
    so the boundary is now stated on every run.  This test is what keeps it
    stated.
    """

    def test_child_processes_are_named_in_the_non_coverage_table(self):
        areas = {item["area"] for item in audio_guard.NON_COVERAGE}
        assert "child processes" in areas
        assert "tool-use soundfonts" in areas

    def test_every_report_carries_the_non_coverage_and_its_scope(self):
        payload = audio_guard.report_payload()
        assert payload["non_coverage"] == audio_guard.NON_COVERAGE
        assert "child process" in payload["verdict_scope"]

    def test_the_verdict_line_is_scoped_to_this_process(self):
        import inspect as _inspect

        from tests.audio_guard import plugin

        source = _inspect.getsource(plugin._Reporter._write_hits)
        assert "IN THIS PROCESS" in source, (
            "the GREEN line claims more than the guard measured"
        )


class TestGuardSurvivesItsOwnDisarming:
    """``importlib.reload(sounddevice)`` removes every guard, silently.

    Silently is the operative word: a reload writes straight into the module's
    ``__dict__``, so the rebinding watcher never sees it, and it builds BRAND
    NEW class objects — so re-installing attribute by attribute would restore
    the module-level functions and leave every stream class unguarded while
    *looking* re-armed.  The teardown check answers a reload as a reload: it
    re-derives and arms again from scratch, and says so as an event.

    The drill INSPECTS and never CALLS while the guard is down.  Calling
    ``sd.play()`` in that window would open the real device of whoever is at
    this machine — which is the thing we are here to prevent, not to prove.
    """

    def test_a_reload_removes_the_guards(self):
        import importlib

        importlib.reload(sd)
        assert not hasattr(sd.play, "__vm2072_audio_guard__"), (
            "expected the reload to remove the guard — if it did not, this "
            "drill is no longer testing anything"
        )

    def test_the_guard_came_back_by_itself(self):
        """Runs immediately after the reload drill, in file order."""
        assert hasattr(sd.play, "__vm2072_audio_guard__"), (
            "the guard did not survive a reload of sounddevice"
        )
        assert hasattr(sd._lib.Pa_OpenStream, "__vm2072_audio_guard__"), (
            "the PortAudio backstop did not come back with the rest"
        )
        events = [e["event"] for e in audio_guard.EVENTS]
        assert "guard-full-rearm" in events, (
            "the reload was repaired without being recorded — a silent repair "
            "is only one bug away from a silent hole"
        )

    def test_the_rearmed_guard_actually_fires(self):
        with expect_blocked("play", label="drill: post-reload"):
            with pytest.raises(AudioDeviceTouchedInTest):
                sd.play(SILENCE, samplerate=44100)


class TestConditionalTriggersMatchArgvStructure:
    """A conditional program is judged on WHERE the trigger appears.

    The triggers were originally tested with ``t in " ".join(argv)``.  Under
    that rule ``piper``'s ``-`` (meaning "write to stdout") matched the dash of
    ``--model``, so EVERY ``piper`` invocation with any flag was blocked, and
    ``ffmpeg -i alsa_capture.wav`` was blocked on a FILENAME.  A false RED costs
    as much as a miss here — hits decide the exit status — so both directions
    are drilled: the structural match still fires on the real thing, and no
    longer fires on the lookalike.
    """

    def test_piper_writing_a_file_is_not_blocked(self):
        """The regression itself: a flag is not a ``-``."""
        match = subprocess_layer._audio_match(
            ["piper", "--model", "en_US.onnx", "--output_file", "/tmp/out.wav"])
        assert match["program"] == "piper"
        assert match["block"] is False, (
            "a piper invocation writing a WAV file was blocked because '-' "
            "was matched as a substring of '--model'"
        )
        assert match["triggers_fired"] == []

    def test_piper_piping_raw_audio_onward_is_still_blocked(self):
        for argv in (["piper", "--model", "x.onnx", "--output-raw"],
                     ["piper", "--output_raw"],
                     ["piper", "-"]):
            match = subprocess_layer._audio_match(argv)
            assert match["block"] is True, argv
            assert match["triggers_fired"], argv

    def test_a_filename_that_merely_reads_like_a_device_is_not_a_device(self):
        match = subprocess_layer._audio_match(
            ["ffmpeg", "-i", "/tmp/alsa_capture.wav", "/tmp/out.mp3"])
        assert match["block"] is False, (
            "a file named alsa_capture.wav is not an audio device"
        )

    def test_an_audio_device_muxer_is_still_blocked_both_spellings(self):
        for argv in (["ffmpeg", "-f", "alsa", "default"],
                     ["ffmpeg", "-f=audiotoolbox", "-"],
                     ["ffmpeg", "-i", "x.wav", "-f", "coreaudio", "default"]):
            match = subprocess_layer._audio_match(argv)
            assert match["block"] is True, argv

    def test_a_word_inside_another_word_is_not_the_word(self):
        """``essay`` is not ``say``; ``Sounds good`` is not ``sound``."""
        for argv in (["osascript", "-e", 'display dialog "essay"'],
                     ["osascript", "-e", 'display dialog "Soundstage"']):
            match = subprocess_layer._audio_match(argv)
            assert match["block"] is False, argv

    def test_a_script_that_really_speaks_is_still_blocked(self):
        for argv in (["osascript", "-e", 'say "hello"'],
                     ["osascript", "-e", "set volume output volume 50"],
                     ["powershell", "-c", "[console]::Beep(440,500)"],
                     ["powershell", "-Command",
                      "(New-Object System.Media.SoundPlayer 'x.wav').Play()"]):
            match = subprocess_layer._audio_match(argv)
            assert match["block"] is True, argv

    def test_the_flag_itself_is_never_the_script(self):
        """``-e`` is an option letter, not AppleScript.

        Only non-flag arguments are searched, so an option that happens to
        contain a trigger word cannot fire one.
        """
        match = subprocess_layer._audio_match(["osascript", "--saymore",
                                               "tell app \"Finder\" to close"])
        assert match["block"] is False

    def test_the_program_is_judged_on_its_own_arguments_only(self):
        """A pipeline's later program does not lend its argv to an earlier one."""
        match = subprocess_layer._audio_match("ffprobe alsa.wav")
        assert match["program"] == "ffprobe"
        assert match["block"] is False

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
    def test_on_the_real_path_the_lookalike_runs_and_is_recorded(self):
        """Not a classification test: a real spawn, through the real guard.

        ``ffmpeg`` really runs (and fails on the missing file, silently — no
        output device is involved). What matters is that the guard ALLOWED it
        and still RECORDED it with its reason.
        """
        before = len(audio_guard.HITS)
        subprocess.run(["ffmpeg", "-i", "/tmp/vm2072-alsa-nonexistent.wav",
                        "-f", "null", "-"],
                       capture_output=True, check=False)
        new = audio_guard.HITS[before:]
        assert len(new) == 1, [h["entry_point"] for h in new]
        assert new[0]["disposition"] == "allowed"
        assert new[0]["triggers_fired"] == []

    def test_on_the_real_path_the_real_thing_is_still_stopped(self):
        """No process is started, so this drill cannot make a sound even if
        ``piper`` were installed."""
        with expect_blocked("subprocess.run", label="drill: piper --output-raw"):
            with pytest.raises(AudioSubprocessSpawnedInTest):
                subprocess.run(["piper", "--model", "x.onnx", "--output-raw"])

    def test_the_judgement_gaps_travel_with_the_report(self):
        """What the tables knowingly do not claim is IN the receipt."""
        gaps = subprocess_layer.census_summary()["known_judgement_gaps"]
        assert gaps and all("why_not_closed" in gap for gap in gaps)


class TestTheGuardNeverClaimsARepairItDidNotPerform:
    """A log that manufactures confidence is the dead-guard family, reversed.

    The plugin used to emit ``guard-rearmed`` for the SUBPROCESS layer, which
    had no ``rearm()`` — a repair announced, never performed, in exactly the
    record a human would consult after an incident.  Found by fix-001's peer
    review.

    Ordering-dependent by design, like the reload drill above: the hole has to
    survive one teardown for the plugin to be the thing that repairs it.  The
    target is ``subprocess.check_output`` deliberately — no drill in this suite
    spawns audio through it, and ``Popen``/``fork_exec`` stay armed underneath
    it regardless, so the window cannot become audible.
    """

    def test_both_layers_can_perform_the_repair_the_plugin_announces(self):
        from tests.audio_guard import sounddevice_layer

        for module in (sounddevice_layer, subprocess_layer):
            assert callable(getattr(module, "rearm", None)), (
                f"{module.__name__} is announced as re-armed but cannot re-arm"
            )

    def test_a_guard_removed_mid_test_is_really_gone(self):
        original = next(o for owner, name, o in subprocess_layer._ORIGINALS
                        if owner is subprocess and name == "check_output")
        subprocess.check_output = original  # not monkeypatch: it must SURVIVE
        assert not hasattr(subprocess.check_output, "__vm2072_audio_guard__")

    def test_the_plugin_repaired_it_and_reported_the_repair_truthfully(self):
        """Runs immediately after the removal, in file order."""
        assert hasattr(subprocess.check_output, "__vm2072_audio_guard__"), (
            "the subprocess layer did not come back — the window stayed open"
        )
        rearmed = [e for e in audio_guard.EVENTS
                   if e["event"] == "guard-rearmed" and e.get("layer") == "subprocess"]
        assert rearmed, "the repair happened but was never recorded"
        assert rearmed[-1]["restored"] == 1, rearmed[-1]

    def test_the_repaired_guard_actually_fires(self):
        with expect_blocked("subprocess.check_output", label="drill: post-rearm"):
            with pytest.raises(AudioSubprocessSpawnedInTest):
                subprocess.check_output(["afplay", "/System/Library/Sounds/Ping.aiff"])

    def test_no_rearm_event_anywhere_claims_a_repair_of_nothing(self):
        for event in audio_guard.EVENTS:
            if event["event"] != "guard-rearmed":
                continue
            assert event["restored"] not in (0, None), event

    def test_a_repair_that_restores_nothing_is_reported_as_a_failure(self):
        """The honest-reporting path, driven directly through the real code."""
        from tests.audio_guard import plugin

        before = len(audio_guard.EVENTS)
        plugin._Reporter._repair(
            "subprocess", subprocess_layer, "<drill>",
            [{"owner": "subprocess", "attribute": "no_such_attribute",
              "found": "NoneType"}],
        )
        new = [e["event"] for e in audio_guard.EVENTS[before:]]
        assert new == ["guard-rearm-failed"], new

    def test_a_layer_that_cannot_rearm_is_not_reported_as_rearmed(self):
        """No such layer today — which is why the branch needs a drill."""
        from tests.audio_guard import plugin

        class LayerWithoutRearm:
            __name__ = "layer_without_rearm"

        before = len(audio_guard.EVENTS)
        plugin._Reporter._repair(
            "stub", LayerWithoutRearm(), "<drill>",
            [{"owner": "stub", "attribute": "x", "found": "NoneType"}],
        )
        new = [e["event"] for e in audio_guard.EVENTS[before:]]
        assert new == ["guard-not-rearmable"], new


class TestEndToEndInAChildRun:
    """The criteria that can only be shown by a WHOLE RUN, run as a whole run.

    A child pytest is spawned on a directory that has never heard of this repo's
    markers, conftest or acceptance.  It demonstrates, in one go:

    * **decay** — a NEW test in a NEW file that NOBODY marked cannot reach the
      device, with no marker list touched by anyone;
    * **exit status from the hit record** — the child's tests all PASS (they
      swallow the guard, as this repo's own code does) and the run still fails;
    * **lifetime** — a crossing from a thread that outlives its test is still
      recorded and attributed to what it outlived;
    * **late reporting** — a crossing after the session ends still reaches the
      person running the suite, on stderr;
    * **visibility of a lifted guard** — ``mock.patch`` of a guarded name is
      recorded as an event rather than passing in silence.
    """

    @pytest.fixture(scope="class")
    def child_run(self, tmp_path_factory):
        workdir = tmp_path_factory.mktemp("audio_guard_e2e")
        (workdir / "conftest.py").write_text(textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(REPO_ROOT)!r})
            from tests.audio_guard import plugin as _guard

            def pytest_configure(config):
                _guard.install(config)
        """))
        # A file nobody has marked, in a directory nobody has configured.
        (workdir / "test_someone_elses_new_test.py").write_text(textwrap.dedent("""
            import threading
            import time
            from unittest import mock

            import numpy as np
            import sounddevice as sd

            SILENCE = np.zeros((1024, 1), dtype=np.float32)

            def test_playback_written_by_someone_who_never_heard_of_the_guard():
                # No marker. No fixture. And it swallows errors, like the repo's
                # own dependencies.py does -- so it PASSES.
                try:
                    sd.play(SILENCE, samplerate=44100)
                except Exception:
                    pass

            def test_thread_that_outlives_me():
                def late():
                    time.sleep(0.05)
                    try:
                        sd.query_devices()
                    except Exception:
                        pass
                threading.Thread(target=late, name="straggler").start()

            def test_running_while_the_straggler_is_still_alive():
                # The straggler's device call lands HERE -- after the teardown of
                # the test that spawned it, where a fixture-scoped guard would
                # already have restored the real functions.
                time.sleep(0.5)

            def test_thread_that_outlives_the_whole_session():
                def very_late():
                    time.sleep(1.5)
                    try:
                        sd.query_devices()
                    except Exception:
                        pass
                threading.Thread(target=very_late, name="after-session").start()

            def test_mock_patch_lifts_a_guard():
                with mock.patch('sounddevice.wait'):
                    pass
        """))
        report = workdir / "report.json"
        env = dict(os.environ)
        env["VOICEMODE_AUDIO_GUARD_REPORT"] = str(report)
        env["VOICEMODE_AUDIO_FEEDBACK"] = "false"
        env["VOICEMODE_SOUNDFONTS_ENABLED"] = "false"
        env.pop("VOICEMODE_TEST_AUDIO_GUARD", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(workdir), "-p", "no:cacheprovider",
             "-q", "--no-header"],
            cwd=str(workdir), env=env, capture_output=True, text=True, timeout=300,
        )
        return proc, json.loads(report.read_text())

    def test_unmarked_new_file_is_blocked_without_anyone_touching_a_marker(self, child_run):
        _, report = child_run
        blocked = [h for h in report["hits"]
                   if h["disposition"] == "blocked"
                   and "test_someone_elses_new_test" in h["nodeid"]]
        assert blocked, "a brand-new unmarked test reached the device"
        assert any(h["entry_point"] == "play" for h in blocked)

    def test_run_fails_on_the_hit_record_although_every_test_passed(self, child_run):
        proc, report = child_run
        # Read pytest's OWN count line, not the whole of stdout: the summary
        # the guard prints is prose, and prose about failure is not failure.
        # (Peer review of fix-001 tripped this by adding the sentence "it is
        # not the fix having failed" to the non-coverage block — a green run
        # reported as a red one, which is the false-positive family this file
        # exists to keep out.)
        counts = [line for line in proc.stdout.splitlines()
                  if re.search(r"\d+ (passed|failed|error)", line)][-1]
        assert "passed" in counts, proc.stdout
        assert "failed" not in counts, proc.stdout
        assert proc.returncode == 1, proc.stdout
        assert report["verdict"] == "RED"
        assert report["failing_hit_count"] >= 1

    def test_crossing_from_a_thread_that_outlived_its_test_is_recorded(self, child_run):
        """The observed device open on this repo happened on a worker thread,
        and a thread can outlive the test that spawned it.  A guard scoped to
        test duration would have restored the real functions by now."""
        _, report = child_run
        straggler = [h for h in report["hits"] if h["thread"] == "straggler"]
        assert straggler, "a crossing from a thread that outlived its test was lost"
        hit = straggler[0]
        assert hit["main_thread"] is False
        assert "test_thread_that_outlives_me" not in hit["nodeid"], (
            "the drill did not actually outlive its test"
        )
        assert hit["disposition"] == "blocked"

    def test_crossing_after_the_session_reaches_stderr(self, child_run):
        proc, _ = child_run
        assert "arrived AFTER the test session finished" in proc.stderr, proc.stderr

    def test_a_lifted_guard_is_visible_as_an_event(self, child_run):
        _, report = child_run
        lifted = [e for e in report["events"] if e["event"] == "guard-lifted"]
        assert lifted, "mock.patch of a guarded name passed in silence"
        assert any(e["attribute"] == "sounddevice.wait" for e in lifted)

# Audio test isolation — the test suite cannot open the real device

**The named thing is the device, not the markers.** A default `pytest` run on
this repo must never open the audio hardware of whoever is at the machine.

This is not hypothetical. For about 24 hours, while three crews worked, this
suite ran through a live human's speakers and microphone: chimes, start/stop
beeps, volume swings, and a garbled voice channel that the agent on the
receiving end logged as *"STT noise"* and quietly worked around. **The defect
did not present as "the tests broke the audio" — it presented as unexplained
flakiness somewhere else entirely**, which is why it survived so long.

## What protects you

Two layers, in this order of importance.

### 1. The guard — `tests/audio_guard/` (needs nobody to remember anything)

Armed at `pytest_configure`, from `tests/conftest.py`, **before a single test
module is imported**. Deliberately *not* an autouse fixture: a fixture is not in
the room for module-level code that pytest executes at collection time, and this
repo has such a file (`tests/test_ffmpeg_demo.py` shells out six times from its
module body — and nobody can put a marker on a module body).

It covers two paths:

| path | what is guarded |
|---|---|
| PortAudio (`sounddevice`) | every device-touching entry point, **derived at arm time** from the installed library; the `_StreamBase.__init__` choke point every stream constructs through; and a backstop on `_lib`, the PortAudio boundary itself |
| process spawns | `subprocess` / `os` / `asyncio` spawn surfaces plus `_posixsubprocess.fork_exec`, because `core.py` shells out to `paplay` and the DJ feature drives `mpv` — **a green device layer does not by itself prove silence** |

Two properties worth knowing:

* **The covered set is derived, never typed.** A hand-written list of this
  repo's audio call sites decayed within one day of being written (10 listed,
  12 real). The guard re-derives its set from the installed `sounddevice` on
  every run.
* **Every process spawn is recorded; only judged-audio spawns are blocked.**
  Which programs make sound is a judgement with no API behind it, so the list is
  never allowed to bound what the guard *knows*: an audio player nobody listed
  shows up in the census as an unrecognised spawn instead of vanishing.

### 2. The marker — `@pytest.mark.audio` (the convenience on top)

Registered in `pyproject.toml`; `-m "not audio"` is in `addopts`. **Expect it to
be forgotten on the next audio-touching test somebody writes** — measured in
this repo, the `slow` and `manual` markers have *zero* users, and the exclusion
that actually works (keeping `tests/manual` out of a default run) is a path rule
that requires nobody's memory. The marker is a convenience; the guard is the
protection.

## Running the tests

```bash
pytest                       # default: audio-marked tests excluded, device unreachable
pytest -m audio              # the opt-in path: runs MUTED (see below)
```

### The opt-in path is muted, not live

`-m audio` puts the guard in **mute** mode: calls are made for real, at the real
entry points, and the guard hands back inert stand-ins without PortAudio ever
being called. Device-safe *by construction*, not by a null sink somebody has to
configure correctly.

**A process spawn is the exception, and it is refused rather than muted.** An
in-process call can be handed a stand-in; `afplay foo.wav` cannot — once it is
exec'd it owns the speakers and this guard is not inside it. So on the opt-in
path an audio spawn raises, and is reported as `REFUSED` rather than `muted`. It
does not fail the run. If you need the program to genuinely run, that is what
`VOICEMODE_TEST_AUDIO_GUARD=off` is for — **ask first if anyone might be on
voice.**

`tests/test_audio_optin_canary.py` occupies that path deliberately — no existing
test needs a real device, so without a canary the opt-in path would ship
untested and be discovered broken by the first person who genuinely needs it.

### If you genuinely need a real device

```bash
VOICEMODE_TEST_AUDIO_GUARD=off pytest tests/whatever.py
```

This announces itself on stderr, in the run header and in the terminal summary,
because a guard that can be absent *silently* is a dead guard. **Ask first if
anyone might be on voice.**

## Reading the output

Every run prints a summary — a clean run must be distinguishable from a run
where nothing armed:

```
VM-2072 AUDIO GUARD — mode=block (default run: the device is unreachable)
  sounddevice: 97 guards on 17 entry points, DERIVED at arm time ...
  PortAudio backstop: installed — 13 symbols deliberately let through
  subprocess: 26 spawn entry points armed; every spawn recorded (14 seen)
  not covered — stated, never silent (3):
    • child processes: ... [14 spawned this run: {'git': 2, 'ffprobe': 11, ...}]
    • tool-use soundfonts: ...
    • VOICEMODE_TEST_AUDIO_GUARD=off runs: ...
RESULT: GREEN — nothing IN THIS PROCESS reached the real audio device
        (see 'not covered' above for the boundary).
```

**Read the verdict's wording as written.** It is scoped on purpose: the guard
sees this process and every thread in it, and it sees *that* a child was
spawned — not what the child did once it was running. One spawn counts once,
even though it crosses three guarded surfaces on the way out.

Set `VOICEMODE_AUDIO_GUARD_REPORT=/path/report.json` for the machine-readable
receipt (every hit, every event, every deliberate non-coverage with its reason).

**The exit status comes from the guard's own hit record, never from pytest's
pass/fail.** Measured here: the code under test swallowed the guard's exception
and the run still reported "10 passed". A blocked call the suite forgives is the
same defect one step later, so a run with an unsanctioned crossing exits
non-zero whatever the tests said.

Other things the summary will tell you rather than hide:

* **`guard-lifted` events** — `mock.patch('sounddevice.wait')` or
  `importlib.reload(sounddevice)` really do remove a guard for a window. That
  window is recorded as an event and the guard is re-armed at teardown.
* **`allowed` spawns** — audio-*capable* programs whose invocation cannot reach
  a device (`ffmpeg -version`) are allowed **and recorded with the reason**. A
  false RED costs as much as a miss: blocking `ffmpeg -version` once aborted
  collection of this suite.
* **Crossings after the session** — a straggler thread's device call still
  reaches stderr after the summary is printed.

## If a test of yours starts failing on the guard

Almost certainly the test is **missing a mock**, not in need of a marker. Every
audio-touching test in this suite when the guard landed was that: the fix was to
mock the seam the test was not asserting about (device enumeration, or the
recording call), which kept all of them in the default run. Reach for
`@pytest.mark.audio` only when the test's *subject* is the audio path itself.

## What this does NOT cover

Stated so that continued noise is not mistaken for a failed fix:

This list is not prose only: it is the `NON_COVERAGE` table in
`tests/audio_guard/__init__.py`, **printed in the terminal summary of every run
and carried in every JSON report**, so it cannot quietly drift out of date.

* **The inside of a child process.** The guard lives in *this* interpreter. It
  records every spawn and blocks judged-audio programs, but a child that opens
  the device *itself* — `python -c "import sounddevice; sd.query_devices()"` —
  is not intercepted and never reaches the hit record. Demonstrated during
  fix-001's peer review: a child enumerated ten real devices while the summary
  said GREEN. Mediated by two things: every spawn *is* in the census, so an
  unrecognised child is visible rather than absent; and rca-001 measured that
  importing all 131 `voice_mode` modules touches no audio, so today's
  `python -m voice_mode` children are quiet at import. **This is why the verdict
  line reads "nothing IN THIS PROCESS".**
* **Tool-use soundfonts** (`VOICEMODE_SOUNDFONTS_ENABLED`, `config.py`, defaults
  **true**) fire on **agent tool calls**, not on test runs. Out of scope here —
  a test-isolation guard cannot address them, because they are not the test
  suite. The guard does set `VOICEMODE_SOUNDFONTS_ENABLED=false` and
  `VOICEMODE_AUDIO_FEEDBACK=false` for the test process (and hence its
  children), so no *test* run emits them, but an agent working normally still
  can.
* **`VOICEMODE_TEST_AUDIO_GUARD=off` runs**, by definition.
* **A module that replaces `sys.modules['sounddevice']` wholesale.** If a file
  does `sys.modules['sounddevice'] = MagicMock()` — in its *module body*, which
  pytest runs at **collection** time, so it stands for the rest of the session —
  then every later import of `sounddevice` returns that object and not the
  guarded module. The guard cannot see through it, and does not pretend to: it
  reports the condition **once**, names **the file responsible**, adds it to
  this table for the rest of the run, and downgrades its verdict to *"GREEN, BUT
  COVERAGE WAS INCOMPLETE"*. (A replacement that is a *real* `sounddevice`
  module is simply adopted — derived and armed — and coverage continues.)
  Anything that imported `sounddevice` **before** the replacement still holds
  the guarded module and is still guarded.

  This one is repairable, unlike the others, and the repair is in the test:
  **patch the seam the code under test uses.** See below.

## Patch the seam, not the module

Two habits look equivalent and are not:

```python
patch('sounddevice.rec')                        # the module attribute
patch('voice_mode.tools.converse.sd.rec')       # the seam the code holds
```

They are the same object *only while* `sys.modules['sounddevice']` is the module
`converse` imported. The moment anything replaces it, the first patches a
stand-in nobody calls and the code under test walks straight to the real device.
Measured in this repo's first full-suite run (2026-08-19): three such calls
reached the audio boundary from two tests that passed in isolation, and one
module-level `sys.modules` assignment silently disabled five of the guard's own
drills — they stopped raising, which is indistinguishable from "there was
nothing to catch".

So:

* **Patch the seam** (`voice_mode.tools.converse.sd.rec`), not the module
  attribute, whenever the code under test holds its own reference.
* **Never replace a module in `sys.modules` at import time.** Its blast radius
  is the whole session, not your file. If a dependency is genuinely optional,
  patch it inside a fixture that restores it.
* Mocks are for the *seam*; the **device** is the guard's job, and the guard
  needs nobody to remember anything.

## Writing a new test that touches audio

1. Mock the seam if the audio is incidental to what you are asserting.
2. If the audio path *is* the subject, mark it `@pytest.mark.audio` — it will run
   only under `-m audio`, muted.
3. Do not remove or weaken `tests/audio_guard/`. Its own drills live in
   `tests/test_audio_guard.py` (fires when it should, and — equally important —
   does not fire when it should not) and `tests/test_audio_guard_decay.py`.

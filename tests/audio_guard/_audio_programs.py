"""VM-2072 — which programs can put sound on this machine.

VENDORED, NOT WRITTEN HERE.  Lifted verbatim from VM-2072 rca-001's
``enumerate_subprocess_spawns.py`` (the judgement tables only; the AST census
that produced the spawn-site survey stayed in the task's evidence directory,
because the guard does not need it at runtime).

THE HONEST SPLIT — READ THIS BEFORE TRUSTING THE TABLES
-------------------------------------------------------
Which programs can produce SOUND is a **judgement**.  There is no API to derive
it from.  It is written down, versioned and printed in every report so it can be
audited — but it is a list, and a list is exactly the thing VM-2072's acceptance
distrusts.

That is why the runtime interceptor (``subprocess_layer``) does **not** rest its
coverage claim on this list: it RECORDS EVERY SPAWN, whatever the program, and
uses the list only to decide what to *block*.  An audio player nobody added to
the table still appears in the census as an unrecognised spawn instead of
vanishing silently.  The list can be incomplete without the measurement going
quiet.
"""

from __future__ import annotations

#: Programs whose very invocation puts sound on the machine, or opens the
#: microphone.  A JUDGEMENT LIST — see the module docstring.  Matched on the
#: executable's BASENAME so ``/usr/bin/afplay`` and ``afplay`` are one thing.
ALWAYS_AUDIO: dict[str, str] = {
    "afplay": "macOS audio file player — plays through the default output device",
    "say": "macOS speech synthesiser — speaks through the default output device",
    "mpv": "media player; the DJ feature drives it (dj/controller.py) — NOT platform-gated",
    "mplayer": "media player, mpv's predecessor",
    "vlc": "media player",
    "cvlc": "VLC's console front end",
    "ffplay": "ffmpeg's player — plays audio directly",
    "paplay": "PulseAudio player (core.py:610, Linux)",
    "pacat": "PulseAudio raw playback",
    "pw-play": "PipeWire player",
    "pw-cat": "PipeWire raw playback",
    "aplay": "ALSA player",
    "arecord": "ALSA recorder — opens the microphone",
    "sox": "audio swiss-army knife; can play and record",
    "play": "sox's playback front end",
    "rec": "sox's record front end — opens the microphone",
    "mpg123": "mp3 player",
    "mpg321": "mp3 player",
    "ogg123": "ogg player",
    "speaker-test": "ALSA tone generator",
    "spd-say": "speech-dispatcher CLI",
    "espeak": "speech synthesiser",
    "espeak-ng": "speech synthesiser",
    "termux-tts-speak": "Android/Termux speech",
}

#: Programs that CAN reach an audio device but usually do not — the decision
#: belongs to the arguments, not the name.
#:
#: WHY THIS TIER EXISTS, AND IT IS NOT A CONVENIENCE.  The first wide run under
#: a name-only block aborted collection: ``tests/test_ffmpeg_demo.py`` runs
#: ``ffmpeg -version`` in its MODULE BODY, which pytest executes at collection.
#: ``ffmpeg -version`` cannot make a sound.  Blocking it was a FALSE RED, and
#: repro-001 §8.7 is explicit that a false RED costs as much as a missed one
#: here — hits decide the exit status, so one phantom fails a whole run and
#: sends someone hunting a device open that never happened, on the one task
#: whose entire history is misattributed audio symptoms.
#:
#: So these are decided on the INVOCATION.  ``ffmpeg`` only reaches speakers
#: when its output muxer is an audio device (``-f audiotoolbox|alsa|pulse|
#: oss|sndio|sdl|sdl2|openal|jack``); ``osascript`` only when the script it is
#: handed mentions speech, a beep, or the volume.  Anything matching a trigger
#: is blocked; anything not is ALLOWED **and still recorded** with the decision
#: and its reason, so a wrong call here is visible in the census rather than
#: silent (repro-001 §8.9 — deliberate non-coverage must be recorded, not just
#: correct).
CONDITIONAL_AUDIO: dict[str, dict] = {
    "ffmpeg": {
        "reason": "can be given an audio output device as its sink",
        "triggers": ["audiotoolbox", "alsa", "pulse", "oss", "sndio",
                     "sdl", "sdl2", "openal", "jack", "coreaudio"],
        "trigger_desc": "an audio-device output muxer (-f <device>)",
        "inert_note": "file/stream transcoding and -version write no audio",
    },
    "ffprobe": {
        "reason": "ffmpeg's inspector; shares the device muxers in principle",
        "triggers": ["audiotoolbox", "alsa", "pulse", "oss", "sndio",
                     "sdl", "sdl2", "openal", "jack", "coreaudio"],
        "trigger_desc": "an audio-device muxer",
        "inert_note": "ffprobe only reads metadata in every normal invocation",
    },
    "osascript": {
        "reason": "can drive `say`/`beep` and set system volume via AppleScript",
        "triggers": ["say", "beep", "volume", "sound"],
        "trigger_desc": "a script mentioning say/beep/volume/sound",
        "inert_note": "AppleScript is used for many non-audio things",
    },
    "powershell": {
        "reason": "can play sound via System.Media on Windows",
        "triggers": ["SoundPlayer", "Beep", "SpeechSynthesizer", "Media."],
        "trigger_desc": "a System.Media / Beep / speech call",
        "inert_note": "inert on this Darwin host in any case",
    },
    "piper": {
        "reason": "neural TTS — writes audio, commonly piped to a player",
        "triggers": ["--output-raw", "--output_raw", "-"],
        "trigger_desc": "raw output, i.e. piped onward rather than to a file",
        "inert_note": "writing a .wav file makes no sound by itself",
    },
}

#: Every audio-capable program, either tier.  Used by the STATIC scan, which
#: only knows names and cannot see arguments.
AUDIO_PROGRAMS: dict[str, str] = {
    **ALWAYS_AUDIO,
    **{name: info["reason"] for name, info in CONDITIONAL_AUDIO.items()},
}

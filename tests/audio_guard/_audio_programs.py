"""VM-2072 — which programs can put sound on this machine.

VENDORED, THEN CORRECTED — AND HERE IS EXACTLY WHERE IT DIVERGES.
The two judgement tables came verbatim from VM-2072 rca-001's
``enumerate_subprocess_spawns.py`` (the tables only; the AST census that
produced the spawn-site survey stayed in the task's evidence directory, because
the guard does not need it at runtime).  ``ALWAYS_AUDIO`` is still verbatim.
``CONDITIONAL_AUDIO`` is **not**: fix-001's peer review found its triggers were
matched as SUBSTRINGS OF THE JOINED ARGV, so ``piper``'s ``"-"`` trigger fired
on any ``piper --anything``.  The programs, the reasons and the trigger
vocabularies are unchanged; what changed is that each entry now says WHERE IN
THE ARGV its trigger has to appear (``match``), and matching is done by
``fired_triggers()`` below.  Nothing was added to or removed from the judgement
itself — see ``KNOWN_JUDGEMENT_GAPS``.

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

import functools
import re

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
#:
#: ⚠️ EACH ENTRY SAYS *WHERE* ITS TRIGGER MUST APPEAR — ``match`` — AND THAT IS
#: NOT DECORATION.  These triggers were originally tested with ``t in
#: " ".join(argv)``, which is a false-RED generator: ``piper``'s ``"-"`` is a
#: substring of ``--model``, so **every** ``piper`` invocation with any flag at
#: all fired it, and ``ffmpeg -i alsa_recording.wav out.mp3`` fired on the
#: filename.  On this task a false RED costs as much as a miss — hits decide the
#: exit status, so one phantom fails a whole suite and sends somebody hunting a
#: device open that never happened, on the one repo whose audio symptoms have
#: already been misattributed once.  Found by fix-001's peer review; the fix is
#: to match argv STRUCTURE (``fired_triggers`` below).
CONDITIONAL_AUDIO: dict[str, dict] = {
    "ffmpeg": {
        "reason": "can be given an audio output device as its sink",
        # `-f alsa` / `--format=alsa`: the muxer is the VALUE OF A FLAG, so a
        # file merely NAMED alsa_capture.wav is not an audio device.
        "match": "flag_value",
        "flags": ["-f", "-format", "--format"],
        "values": ["audiotoolbox", "alsa", "pulse", "oss", "sndio",
                   "sdl", "sdl2", "openal", "jack", "coreaudio"],
        "trigger_desc": "an audio-device output muxer (-f <device>)",
        "inert_note": "file/stream transcoding and -version write no audio",
    },
    "ffprobe": {
        "reason": "ffmpeg's inspector; shares the device muxers in principle",
        "match": "flag_value",
        "flags": ["-f", "-format", "--format"],
        "values": ["audiotoolbox", "alsa", "pulse", "oss", "sndio",
                   "sdl", "sdl2", "openal", "jack", "coreaudio"],
        "trigger_desc": "an audio-device muxer",
        "inert_note": "ffprobe only reads metadata in every normal invocation",
    },
    "osascript": {
        "reason": "can drive `say`/`beep` and set system volume via AppleScript",
        # The AppleScript itself is an ARGUMENT (`-e <script>` or a .scpt path),
        # never a flag — and the words are matched on WORD BOUNDARIES, so
        # "essay" and "Sounds good" no longer read as speech.
        "match": "script_word",
        "words": ["say", "beep", "volume", "sound"],
        "trigger_desc": "a script mentioning say/beep/volume/sound",
        "inert_note": "AppleScript is used for many non-audio things",
    },
    "powershell": {
        "reason": "can play sound via System.Media on Windows",
        "match": "script_word",
        "words": ["SoundPlayer", "Beep", "SpeechSynthesizer", "Media."],
        "trigger_desc": "a System.Media / Beep / speech call",
        "inert_note": "inert on this Darwin host in any case",
    },
    "piper": {
        "reason": "neural TTS — writes audio, commonly piped to a player",
        # `-` means stdout by long-standing convention: it is a WHOLE ARGUMENT,
        # not a character somewhere in one. As a substring it fired on every
        # flag in the argv, which is the defect this entry is named after.
        "match": "exact_token",
        "tokens": ["--output-raw", "--output_raw", "-"],
        "trigger_desc": "raw output, i.e. piped onward rather than to a file",
        "inert_note": "writing a .wav file makes no sound by itself",
    },
}

#: JUDGEMENT GAPS THAT ARE KNOWN AND DELIBERATELY NOT CLOSED HERE.
#:
#: Recorded rather than fixed, because widening the judgement is a different
#: decision from correcting how it is matched, and this pass is the latter.
#: Carried into the guard's JSON report so the gap travels with the evidence
#: instead of living only in somebody's memory (POLICY 4c: deliberate
#: non-coverage ships stated, never silent).
KNOWN_JUDGEMENT_GAPS: list = [
    {
        "program": "ffmpeg",
        "gap": "the CAPTURE side is not in `values`: `-f avfoundation` (macOS) "
               "and `-f dshow` (Windows) open the MICROPHONE rather than the "
               "speakers, and would be ALLOWED (recorded, not blocked)",
        "why_not_closed": "rca-001's census of 249 spawn sites found no such "
                          "invocation in this repo; widening the judgement is "
                          "a scope decision for whoever needs it, and every "
                          "such spawn is recorded in the census either way",
    },
    {
        "program": "<any>",
        "gap": "a program that makes sound and is in NEITHER table is allowed",
        "why_not_closed": "unclosable in principle — which is why the guard "
                          "RECORDS EVERY SPAWN and only uses these tables to "
                          "decide what to BLOCK: an unlisted player appears in "
                          "the census as an unrecognised spawn rather than "
                          "vanishing",
    },
]


@functools.lru_cache(maxsize=256)
def _word_pattern(word: str):
    """A word-boundary matcher that also works for non-identifier triggers.

    ``\\b`` is wrong at a non-word edge: ``Media.`` ends in a dot, where
    ``\\b`` would demand a following word character.  So the boundary is
    asserted only on the edges that are actually word characters.
    """
    left = r"(?<!\w)" if (word[:1].isalnum() or word[:1] == "_") else ""
    right = r"(?!\w)" if (word[-1:].isalnum() or word[-1:] == "_") else ""
    return re.compile(left + re.escape(word) + right, re.IGNORECASE)


def _match_flag_value(info: dict, argv: list) -> list:
    """Fire when a WATCHED FLAG's VALUE is an audio device.

    Handles both spellings ffmpeg accepts: ``-f alsa`` and ``-f=alsa``.
    """
    flags = set(info["flags"])
    values = {value.lower() for value in info["values"]}
    fired = []
    for index, token in enumerate(argv):
        flag, sep, inline = token.partition("=")
        if flag not in flags:
            continue
        if sep:
            value = inline
        elif index + 1 < len(argv):
            value = argv[index + 1]
        else:
            continue
        if value.lower() in values:
            fired.append(f"{flag} {value}")
    return fired


def _match_exact_token(info: dict, argv: list) -> list:
    """Fire only on a WHOLE argument, never on a character inside one."""
    wanted = set(info["tokens"])
    return [token for token in dict.fromkeys(argv) if token in wanted]


def _match_script_word(info: dict, argv: list) -> list:
    """Fire on a WORD inside a script-bearing ARGUMENT.

    Only non-flag arguments are searched — the script is what ``-e`` (or
    ``-Command``) is handed, or a path, never the option letter itself — and
    the search is word-bounded, so ``essay`` is not ``say`` and ``Sounds
    good`` is not ``sound``.
    """
    fired = []
    for token in argv:
        if token.startswith("-") and token != "-":
            continue  # an option flag is not a script
        for word in info["words"]:
            if word not in fired and _word_pattern(word).search(token):
                fired.append(word)
    return fired


_MATCHERS = {
    "flag_value": _match_flag_value,
    "exact_token": _match_exact_token,
    "script_word": _match_script_word,
}


def fired_triggers(program: str, argv: list) -> list:
    """Which of ``program``'s triggers this invocation actually fires.

    ``argv`` is the tokens AFTER the program name — a program's arguments come
    after it, whether it was found at ``argv[0]`` or in the middle of a shell
    pipeline.  Empty list means "audio-capable program, inert invocation":
    ALLOWED, and still recorded.
    """
    info = CONDITIONAL_AUDIO[program]
    matcher = _MATCHERS[info["match"]]
    return matcher(info, [token for token in argv if isinstance(token, str)])

#: Every audio-capable program, either tier.  Used by the STATIC scan, which
#: only knows names and cannot see arguments.
AUDIO_PROGRAMS: dict[str, str] = {
    **ALWAYS_AUDIO,
    **{name: info["reason"] for name, info in CONDITIONAL_AUDIO.items()},
}

"""mouth CLI: say, stop, status, devices, voices, resolve, render, audio, serve.  ``python -m voice_mode.mouth --help``"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import amend, play, retract, say, status, stop


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mouth", description="speak back: say returns at once")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("say", help="queue TEXT ('-' reads stdin); prints the utterance id")
    s.add_argument("text", nargs="+")
    s.add_argument("--voice", help="a clone (pip, laurie) or a kokoro voice (af_sky); else the "
                   "settings file's voice, $VOICEMODE_MOUTH_VOICE, af_sky (`mouth voices`)")
    s.add_argument("--speed", type=float)
    s.add_argument("--backend", choices=["auto", "kokoro", "clone", "silence"])
    s.add_argument("--device", help="exact output device name, 'null', 'default', or call:<N> (a live "
                   "Delta Chat call, `mouth devices`); $VOICEMODE_MOUTH_DEVICE")
    side = s.add_mutually_exclusive_group()
    side.add_argument("--pan", type=float, help="-1 left ear only .. 1 right ear only; $VOICEMODE_MOUTH_PAN")
    side.add_argument("--channel", choices=["left", "right", "both"], help="--pan -1 / 1 / none")
    s.add_argument("--log-dir", type=Path, help="write saying/said here, not the real heard log")
    s.add_argument("--wait", action="store_true", help="block until said; print it")
    s.add_argument("--hold", choices=["turn-end"],
                   help="wait for the end of his turn (the ears' heard log), then speak")
    s.add_argument("--interest", choices=["high", "normal", "low", "zero"],
                   help="how much you want his reply: high (wake on his partials), normal (his "
                        "turn), low, zero (speak and leave); read by heard-first reply:AGENT")
    s.add_argument("--expires", type=float, metavar="S",
                   help="drop the line, unspoken, if it has not started S seconds from now")
    pri = s.add_mutually_exclusive_group()
    pri.add_argument("--next", dest="priority", action="store_const", const="next",
                     help="the front of the queue (priority 0)")
    pri.add_argument("--now", dest="priority", action="store_const", const="now",
                     help="interrupt the line playing now, then speak")
    pri.add_argument("--priority", dest="priority", metavar="N",
                     help="a place in the playlist: lower plays sooner; next is 0, none is 50")

    pl = sub.add_parser("play", help="queue a sound file or URL, or a section of it")
    pl.add_argument("source")
    pl.add_argument("--start", type=float, help="seconds into the file")
    pl.add_argument("--end", type=float, help="seconds into the file")
    pl.add_argument("--device")
    pside = pl.add_mutually_exclusive_group()
    pside.add_argument("--pan", type=float)
    pside.add_argument("--channel", choices=["left", "right", "both"])
    pl.add_argument("--log-dir", type=Path)
    pl.add_argument("--wait", action="store_true")
    ppri = pl.add_mutually_exclusive_group()
    ppri.add_argument("--next", dest="priority", action="store_const", const="next")
    ppri.add_argument("--now", dest="priority", action="store_const", const="now")

    m = sub.add_parser("amend", help="rewrite a queued line in place (before it is spoken)")
    m.add_argument("utt")
    m.add_argument("text", nargs="+")
    r = sub.add_parser("retract", help="drop a queued line, or cut it if it is playing")
    r.add_argument("utt")

    t = sub.add_parser("stop", help="cut what is playing, and flush the queue")
    t.add_argument("--reason", default="stop", help="stop (default) or barge-in")
    t.add_argument("--current", action="store_true", help="cut only what is playing; keep the queue")

    sub.add_parser("status", help="player, queue, what is playing")
    ml = sub.add_parser("mail", help="the player, resident on the queue maildir (mail to mouth@<host> lands there)")
    ml.add_argument("--box", type=Path, help="the maildir (default ~/.mail/agents/mouth)")
    ml.add_argument("--once", action="store_true", help="speak what is in new/, then exit")
    sub.add_parser("devices", help="output device names, exactly as --device takes them")
    sub.add_parser("voices", help="JSON: the default voice, where it came from, and every voice")
    rv = sub.add_parser("resolve", help="JSON: what a --voice expression speaks with (a clone's "
                        "reference clip, or kokoro); exit 2, with the reason, if it does not resolve")
    rv.add_argument("voice", help="a name (pip, af_sky), group/voice, voice[N] or group/voice/clip.wav")
    rv.add_argument("--backend", default="auto", choices=["auto", "kokoro", "clone"])
    rn = sub.add_parser("render", help="synthesise TEXT to a WAV file without playing it; "
                        "JSON out (play it later with `mouth play FILE`)")
    rn.add_argument("text", nargs="+")
    rn.add_argument("--voice", required=True, help="as for say, e.g. group/voice/clip.wav")
    rn.add_argument("--out", required=True, type=Path, help="the WAV to write")
    rn.add_argument("--speed", type=float)
    rn.add_argument("--backend", default="auto", choices=["auto", "kokoro", "clone"])
    rn.add_argument("--if-missing", action="store_true", help="make nothing if --out exists")
    au = sub.add_parser("audio", help="JSON lines: the lines the mouth kept (a WAV each), newest first")
    au.add_argument("--voice", help="only this voice's lines")
    au.add_argument("--last", type=int, help="at most this many")
    v = sub.add_parser("serve", help="run the player in the foreground (say starts one for you)")
    v.add_argument("--idle", type=float, help="exit after this long with nothing queued (default 600 s)")

    a = ap.parse_args(argv)
    if a.cmd == "say":
        text = sys.stdin.read() if a.text == ["-"] else " ".join(a.text)
        pan = a.channel or a.pan
        try:
            r = say(text.strip(), voice=a.voice, speed=a.speed, backend=a.backend, device=a.device,
                    pan=pan, log_dir=a.log_dir, wait=a.wait, priority=a.priority,
                    hold=a.hold, expires_s=a.expires, interest=a.interest)
        except (ValueError, TimeoutError) as e:
            print(str(e), file=sys.stderr)
            return 2
        print(json.dumps(r) if a.wait else r["utt"])
        return 0 if not a.wait or r.get("reason") == "done" else 1
    if a.cmd == "play":
        try:
            r = play(a.source, start=a.start, end=a.end, device=a.device, pan=a.channel or a.pan,
                     log_dir=a.log_dir, wait=a.wait, priority=a.priority)
        except (ValueError, TimeoutError) as e:
            print(str(e), file=sys.stderr)
            return 2
        print(json.dumps(r) if a.wait else r["utt"])
        return 0 if not a.wait or r.get("reason") == "done" else 1
    if a.cmd in ("amend", "retract"):
        try:
            r = amend(a.utt, " ".join(a.text)) if a.cmd == "amend" else retract(a.utt)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(json.dumps(r))
        return 0
    if a.cmd == "stop":
        print(json.dumps(stop(a.reason, flush=not a.current)))
        return 0
    if a.cmd == "mail":
        from .inbox import watch

        if a.once:
            return watch(a.box, once=True)
        import signal

        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # so 'disabled' is logged
        return watch(a.box)
    if a.cmd == "status":
        print(json.dumps(status()))
        return 0
    if a.cmd == "devices":
        from .output import live_calls, output_names

        names = output_names(rescan=False)
        names += [f"call:{c}\t# live call, {who}" for c, who, _ in live_calls()]
        print("\n".join(names))
        return 0
    if a.cmd == "voices":
        from .voices import voices

        print(json.dumps(voices()))
        return 0
    if a.cmd == "resolve":
        from .backends import resolve as _resolve

        try:
            be, voice = _resolve(a.backend, a.voice)
        except ValueError as e:
            print(f"mouth resolve: {e}", file=sys.stderr)
            return 2
        extra = getattr(be, "extra_body", {}) or {}
        print(json.dumps({"voice": a.voice, "backend": be.name, "sends": voice,
                          "ref_audio": extra.get("ref_audio"), "ref_text": extra.get("ref_text")},
                         ensure_ascii=False))
        return 0
    if a.cmd == "render":
        from .audio import render

        text = sys.stdin.read() if a.text == ["-"] else " ".join(a.text)
        try:
            info = render(a.voice, text, a.out, backend=a.backend, speed=a.speed,
                          if_missing=a.if_missing)
        except ValueError as e:
            print(f"mouth render: {e}", file=sys.stderr)
            return 2
        print(json.dumps(info, ensure_ascii=False))
        return 0
    if a.cmd == "audio":
        from .audio import kept

        for meta in kept(voice=a.voice, last=a.last):
            print(json.dumps(meta, ensure_ascii=False))
        return 0
    if a.cmd == "serve":
        import signal

        from .player import serve

        # A TERM (a restart between utterances) must run serve's cleanup:
        # release the lock and remove player.pid, not leave a stale one.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        return serve(idle_exit_s=a.idle)
    return 1


if __name__ == "__main__":
    sys.exit(main())

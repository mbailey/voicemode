"""mouth CLI: say, stop, status, devices, serve.  ``python -m voice_mode.mouth --help``"""

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
    s.add_argument("--voice", help="a clone (pip, laurie) or a kokoro voice (af_sky); $VOICEMODE_MOUTH_VOICE")
    s.add_argument("--speed", type=float)
    s.add_argument("--backend", choices=["auto", "kokoro", "clone", "silence"])
    s.add_argument("--device", help="exact output device name, 'null', or 'default'; $VOICEMODE_MOUTH_DEVICE")
    side = s.add_mutually_exclusive_group()
    side.add_argument("--pan", type=float, help="-1 left ear only .. 1 right ear only; $VOICEMODE_MOUTH_PAN")
    side.add_argument("--channel", choices=["left", "right", "both"], help="--pan -1 / 1 / none")
    s.add_argument("--log-dir", type=Path, help="write saying/said here, not the real heard log")
    s.add_argument("--wait", action="store_true", help="block until said; print it")
    pri = s.add_mutually_exclusive_group()
    pri.add_argument("--next", dest="priority", action="store_const", const="next",
                     help="the front of the queue")
    pri.add_argument("--now", dest="priority", action="store_const", const="now",
                     help="interrupt the line playing now, then speak")

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
    ml = sub.add_parser("mail", help="watch mouth@<host>: each mail becomes a line (mail feeds mouth)")
    ml.add_argument("--box", type=Path, help="the maildir (default ~/.mail/agents/mouth)")
    ml.add_argument("--once", action="store_true", help="one pass over new/, then exit")
    sub.add_parser("devices", help="output device names, exactly as --device takes them")
    v = sub.add_parser("serve", help="run the player in the foreground (say starts one for you)")
    v.add_argument("--idle", type=float, help="exit after this long with nothing queued (default 600 s)")

    a = ap.parse_args(argv)
    if a.cmd == "say":
        text = sys.stdin.read() if a.text == ["-"] else " ".join(a.text)
        pan = a.channel or a.pan
        try:
            r = say(text.strip(), voice=a.voice, speed=a.speed, backend=a.backend, device=a.device,
                    pan=pan, log_dir=a.log_dir, wait=a.wait, priority=a.priority)
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
        from .inbox import mail_box, process_new, watch

        if a.once:
            for r in process_new(a.box or mail_box()):
                print(json.dumps(r))
            return 0
        return watch(a.box)
    if a.cmd == "status":
        print(json.dumps(status()))
        return 0
    if a.cmd == "devices":
        from .output import output_names

        print("\n".join(output_names(rescan=False)))
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

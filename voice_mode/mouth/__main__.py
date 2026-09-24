"""mouth CLI: say, stop, status, devices, serve.  ``python -m voice_mode.mouth --help``"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import say, status, stop


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

    t = sub.add_parser("stop", help="cut what is playing, and flush the queue")
    t.add_argument("--reason", default="stop", help="stop (default) or barge-in")
    t.add_argument("--current", action="store_true", help="cut only what is playing; keep the queue")

    sub.add_parser("status", help="player, queue, what is playing")
    sub.add_parser("devices", help="output device names, exactly as --device takes them")
    v = sub.add_parser("serve", help="run the player in the foreground (say starts one for you)")
    v.add_argument("--idle", type=float, help="exit after this long with nothing queued (default 600 s)")

    a = ap.parse_args(argv)
    if a.cmd == "say":
        text = sys.stdin.read() if a.text == ["-"] else " ".join(a.text)
        pan = a.channel or a.pan
        try:
            r = say(text.strip(), voice=a.voice, speed=a.speed, backend=a.backend, device=a.device,
                    pan=pan, log_dir=a.log_dir, wait=a.wait)
        except (ValueError, TimeoutError) as e:
            print(str(e), file=sys.stderr)
            return 2
        print(json.dumps(r) if a.wait else r["utt"])
        return 0 if not a.wait or r.get("reason") == "done" else 1
    if a.cmd == "stop":
        print(json.dumps(stop(a.reason, flush=not a.current)))
        return 0
    if a.cmd == "status":
        print(json.dumps(status()))
        return 0
    if a.cmd == "devices":
        from .output import output_names

        print("\n".join(output_names(rescan=False)))
        return 0
    if a.cmd == "serve":
        from .player import serve

        return serve(idle_exit_s=a.idle)
    return 1


if __name__ == "__main__":
    sys.exit(main())

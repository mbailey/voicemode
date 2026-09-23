"""Arm ``listen`` from a shell and print its return as JSON.

    python -m voice_mode.listen --source file:X.wav --age 8 --log PATH

Exit 0 on any clean return (turn, ceiling, stop, eof), 1 on reason
``error``, 2 on bad arguments. SIGINT/SIGTERM ask it to stop (reason
``stop``), so the ``listen stopped`` line is always written.

It only ever opens an INPUT: no TTS, no playback, no conch.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading

from .chunker import Chunker
from .detector import DEFAULT_SILENCE_S, SilenceTurnDetector
from .loop import DEFAULT_AGE_S, DEFAULT_CEILING_S, DEFAULT_HEARTBEAT_S, listen
from .sink import JsonlSink
from .sources import SourceError, open_source
from .stt import DEFAULT_WHISPER_MODEL, DEFAULT_WHISPER_URL, WhisperSTT


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m voice_mode.listen",
        description="listen spike (VM-2274): write what is heard; return on an aged turn.",
    )
    p.add_argument("--source", default="mic", help="'mic' or 'file:PATH.wav' (default: mic)")
    p.add_argument("--log", required=True, help="JSONL file to append lines to (provisional sink)")
    p.add_argument("--age", type=float, default=DEFAULT_AGE_S, help="return once the newest turn is this old, seconds (default: %(default)s)")
    p.add_argument("--ceiling", type=float, default=DEFAULT_CEILING_S, help="return after this long regardless, seconds (default: %(default)s)")
    p.add_argument("--heartbeat", type=float, default=DEFAULT_HEARTBEAT_S, help="heartbeat period, seconds; 0 disables (default: %(default)s)")
    p.add_argument("--silence", type=float, default=DEFAULT_SILENCE_S, help="silence that ends a turn, seconds (default: %(default)s)")
    p.add_argument("--quiet", type=float, default=0.35, help="quiet that cuts a partial chunk, seconds (default: %(default)s)")
    p.add_argument("--max-chunk", type=float, default=5.0, help="longest chunk before a forced cut, seconds (default: %(default)s)")
    p.add_argument("--no-pace", action="store_true", help="feed a file source as fast as possible, not at real time")
    p.add_argument("--device", default=None, help="mic input device (index or name; default: the system input)")
    p.add_argument("--stt-url", default=DEFAULT_WHISPER_URL, help="OpenAI-compatible STT base URL (default: %(default)s)")
    p.add_argument("--stt-model", default=DEFAULT_WHISPER_MODEL, help="STT model name (default: %(default)s)")
    p.add_argument("--keep-annotations", action="store_true", help="keep whisper's non-speech tags ('(static)', '[BLANK_AUDIO]') as text")
    p.add_argument("--session", default=os.getenv("CLAUDE_SESSION_ID"), help="session id to stamp on lines")
    p.add_argument("--agent", default=os.getenv("VOICEMODE_AGENT"), help="agent name to stamp on lines")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    device = int(args.device) if args.device is not None and args.device.isdigit() else args.device
    try:
        source = open_source(args.source, realtime=not args.no_pace, device=device)
    except SourceError as exc:
        print(json.dumps({"reason": "error", "text": "", "cursor": 0, "error": str(exc)}))
        return 1
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    stt = WhisperSTT(args.stt_url, model=args.stt_model, drop_annotations=not args.keep_annotations)
    try:
        result = listen(
            source,
            JsonlSink(args.log),
            stt,
            age=args.age,
            ceiling=args.ceiling,
            heartbeat=args.heartbeat,
            detector=SilenceTurnDetector(args.silence),
            chunker=Chunker(quiet_s=args.quiet, max_s=args.max_chunk),
            stop=stop,
            session=args.session,
            agent=args.agent,
        )
    finally:
        stt.close()
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 1 if result.reason == "error" else 0


if __name__ == "__main__":
    sys.exit(main())

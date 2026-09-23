"""Run capture, "the ears", from a shell; print its result as JSON on exit.

    python -m voice_mode.listen capture --source mic --device C930e
    python -m voice_mode.listen capture --source file:X.wav [--tail-silence 10]

It writes through ``heard`` (``$VOICEMODE_BASE_DIR/logs/conversations/``,
or ``--log-dir``) and runs until stopped: SIGINT/SIGTERM or ``--stop-file``
(reason ``stop``), an error, the end of a file source (``eof``), or
``--ceiling`` if given. It does not return on a turn. Exit 0 on a clean
stop, 1 on reason ``error``, 2 on bad arguments.

It only ever opens an INPUT: no TTS, no playback, no conch.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

from .. import heard
from .chunker import Chunker
from .detector import DEFAULT_SILENCE_S, SilenceTurnDetector
from .loop import DEFAULT_HEARTBEAT_S, capture
from .sink import HeardSink
from .sources import SourceError, open_source
from .stt import DEFAULT_WHISPER_MODEL, DEFAULT_WHISPER_URL, WhisperSTT


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m voice_mode.listen", description="listen spike (VM-2274)")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser(
        "capture",
        help="the ears: capture and write what is heard until stopped",
        description="Capture (M1): write started/heartbeat/partial/turn/stopped through heard, until stopped.",
    )
    c.add_argument("--source", default="mic", help="'mic' or 'file:PATH.wav' (default: mic)")
    c.add_argument("--device", default=None, help="mic input: an index, or a case-insensitive substring of its name (e.g. C930e)")
    c.add_argument("--log-dir", default=None, help="write heard_YYYY-MM-DD.jsonl here instead of $VOICEMODE_BASE_DIR/logs/conversations")
    c.add_argument("--heartbeat", type=float, default=DEFAULT_HEARTBEAT_S, help="heartbeat period, seconds; 0 disables (default: %(default)s)")
    c.add_argument("--ceiling", type=float, default=None, help="stop after this many seconds (default: none)")
    c.add_argument("--stop-file", default=None, help="stop (reason stop) once this file exists")
    c.add_argument("--silence", type=float, default=DEFAULT_SILENCE_S, help="silence that ends a turn, seconds (default: %(default)s)")
    c.add_argument("--quiet", type=float, default=0.35, help="quiet that cuts a partial chunk, seconds (default: %(default)s)")
    c.add_argument("--max-chunk", type=float, default=2.0, help="longest chunk before a soft cut, seconds; sets how soon a partial lands while speech goes on (default: %(default)s)")
    c.add_argument("--cut-window", type=float, default=0.4, help="a max-length chunk is cut at the quietest frame of its last this-many seconds (default: %(default)s)")
    c.add_argument("--no-pace", action="store_true", help="feed a file source as fast as possible, not at real time")
    c.add_argument("--tail-silence", type=float, default=0.0, help="seconds of silence fed after a file source ends (default: %(default)s)")
    c.add_argument("--stt-url", default=DEFAULT_WHISPER_URL, help="OpenAI-compatible STT base URL (default: %(default)s)")
    c.add_argument("--stt-model", default=DEFAULT_WHISPER_MODEL, help="STT model name (default: %(default)s)")
    c.add_argument("--keep-annotations", action="store_true", help="keep whisper's non-speech tags ('(static)', '[BLANK_AUDIO]') as text")
    c.add_argument("--session", default=heard.caller_session(), help="session id stamped on lines (default: from the environment)")
    c.add_argument("--agent", default=heard.caller_agent(), help="agent name stamped on lines (default: from the environment)")
    return p


def _error_json(msg: str) -> str:
    return json.dumps({"reason": "error", "text": "", "cursor": 0, "error": msg})


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = open_source(args.source, realtime=not args.no_pace, device=args.device, tail_silence_s=args.tail_silence)
    except SourceError as exc:
        print(_error_json(str(exc)))
        return 1
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    stt = WhisperSTT(args.stt_url, model=args.stt_model, drop_annotations=not args.keep_annotations)
    try:
        result = capture(
            source,
            stt,
            HeardSink(Path(args.log_dir) if args.log_dir else None),
            heartbeat=args.heartbeat,
            ceiling=args.ceiling,
            detector=SilenceTurnDetector(args.silence),
            chunker=Chunker(quiet_s=args.quiet, max_s=args.max_chunk, cut_window_s=args.cut_window),
            stop=stop,
            stop_file=args.stop_file,
            session=args.session,
            agent=args.agent,
        )
    finally:
        stt.close()
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 1 if result.reason == "error" else 0


if __name__ == "__main__":
    sys.exit(main())

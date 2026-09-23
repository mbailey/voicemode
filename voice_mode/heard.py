#!/usr/bin/env python3
"""heard - what VoiceMode hears, one JSON line per partial, turn or event.

The log is ``$VOICEMODE_BASE_DIR/logs/conversations/heard_YYYY-MM-DD.jsonl``,
a sibling of ``exchanges_YYYY-MM-DD.jsonl`` that rolls at the same local
midnight (ambient-listen Q6). Append-only: a line is never edited or
removed; a correction is a new line.

Every writer (``listen``, ``converse``, kin's Delta bridge) writes the same
shape through the same contract, so one reader serves every source:

1. take an exclusive ``flock`` on ``heard.lock`` beside the logs (one lock
   for every day's file, so two writers either side of midnight cannot mint
   the same ``seq``);
2. ``seq`` = the last ``seq`` in the newest ``heard_*.jsonl`` + 1. It keeps
   counting across midnight, so a ``seq`` names one line on its own and a
   cursor is one integer;
3. append the record as ONE ``write()`` of ``json + "\\n"`` to a file opened
   ``O_APPEND``, so a reader never sees half a line in practice;
4. release the lock.

This module imports nothing from ``voice_mode`` and nothing outside the
standard library, on purpose: the ride-along hook runs this same file as a
script on every tool call, under whatever ``python3`` is on PATH, and must
start fast and never fail on an import.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA = 1

# kind
PARTIAL = "partial"
TURN = "turn"
EVENT = "event"
KINDS = (PARTIAL, TURN, EVENT)

# event names (kebab-case; the design's "listen started" etc.)
EV_LISTEN_STARTED = "listen-started"
EV_LISTEN_STOPPED = "listen-stopped"
EV_HEARTBEAT = "heartbeat"
EV_DEVICE_CHANGED = "device-changed"
EV_WAKE_WORD = "wake-word"
EV_END_WORD = "end-word"
EV_BARGE_IN = "barge-in"
EV_CALL_STARTED = "call-started"
EV_CALL_ENDED = "call-ended"

LOCK_NAME = "heard.lock"
RESERVED = frozenset({"ts", "seq", "kind", "v"})
_TAIL_BYTES = 64 * 1024


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

def base_dir() -> Path:
    """``$VOICEMODE_BASE_DIR`` or ``~/.voicemode`` (the same rule as config)."""
    raw = os.environ.get("VOICEMODE_BASE_DIR") or str(Path.home() / ".voicemode")
    return Path(os.path.expanduser(os.path.expandvars(raw)))


def log_dir() -> Path:
    return base_dir() / "logs" / "conversations"


def log_path(day: Optional[date] = None, directory: Optional[Path] = None) -> Path:
    day = day or datetime.now().date()
    return (directory or log_dir()) / f"heard_{day.strftime('%Y-%m-%d')}.jsonl"


def log_files(directory: Optional[Path] = None) -> list[Path]:
    """Every heard log in the directory, oldest first (the name sorts by date)."""
    d = directory or log_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("heard_????-??-??.jsonl") if p.is_file())


# --------------------------------------------------------------------------
# Reading the tail of a file
# --------------------------------------------------------------------------

def _last_seq_in(path: Path) -> Optional[int]:
    """The ``seq`` of the last whole, parseable line in ``path``, or None.

    Reads at most the last 64 KiB. A final line with no trailing newline is
    a write in flight (or a torn one) and is skipped, not trusted.
    """
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return None
            f.seek(max(0, size - _TAIL_BYTES))
            chunk = f.read()
    except OSError:
        return None
    lines = chunk.split(b"\n")
    # lines[-1] is b"" when the file ends in a newline; otherwise it is a
    # partial line. Either way it is not a whole record.
    for raw in reversed(lines[:-1]):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        seq = rec.get("seq") if isinstance(rec, dict) else None
        if isinstance(seq, int):
            return seq
    return None


def last_seq(directory: Optional[Path] = None) -> int:
    """The highest ``seq`` written so far, across days; 0 when none."""
    for path in reversed(log_files(directory)):
        seq = _last_seq_in(path)
        if seq is not None:
            return seq
    return 0


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def append(kind: str,
           *,
           text: Optional[str] = None,
           source: str = "mic",
           device: Optional[str] = None,
           session: Optional[str] = None,
           agent: Optional[str] = None,
           final: Optional[bool] = None,
           event: Optional[str] = None,
           directory: Optional[Path] = None,
           **extra: Any) -> dict:
    """Append one record and return it, ``seq`` and ``ts`` filled in.

    ``kind`` is ``partial``, ``turn`` or ``event``. ``final`` defaults to
    False for a partial and True for a turn. Extra keyword fields (``via``,
    ``detector``, ``age_at_return``, ``word``, ``listen_id`` ...) are written
    as given; None values are dropped. Raises ValueError on a bad kind, and
    OSError if the log cannot be written: callers that must not fail
    (``converse``) wrap the call; a listener that cannot write should stop
    and say so.
    """
    if kind not in KINDS:
        raise ValueError(f"heard: kind must be one of {KINDS}, not {kind!r}")
    if kind in (PARTIAL, TURN) and not isinstance(text, str):
        raise ValueError(f"heard: a {kind} needs text")
    if kind == EVENT and not event:
        raise ValueError("heard: an event needs its name (event=...)")
    clash = RESERVED & extra.keys()
    if clash:
        raise ValueError(f"heard: {sorted(clash)} are the writer's to set, not the caller's")
    if final is None and kind != EVENT:
        final = kind == TURN

    d = directory or log_dir()
    d.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(d / LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        record = _clean({
            "ts": _now_iso(),
            "seq": last_seq(d) + 1,
            "kind": kind,
            "event": event,
            "text": text,
            "source": source,
            "device": device,
            "session": session,
            "agent": agent,
            "final": final,
            **extra,
            "v": SCHEMA,
        })
        line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        path = log_path(directory=d)
        fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            written = os.write(fd, line)
            if written != len(line):  # never seen on a local disk; say so if it is
                raise OSError(errno.EIO, f"heard: short write {written}/{len(line)} to {path}")
        finally:
            os.close(fd)
        return record
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def partial(text: str, **kw: Any) -> dict:
    """A recognised chunk that a later turn will subsume (``final: false``)."""
    return append(PARTIAL, text=text, **kw)


def turn(text: str, *, detector: Optional[str] = None, **kw: Any) -> dict:
    """A finished turn: the joined text, and the detector that ended it."""
    return append(TURN, text=text, detector=detector, **kw)


def event(name: str, **kw: Any) -> dict:
    """An event line: listen-started, heartbeat, listen-stopped, wake-word ..."""
    return append(EVENT, event=name, **kw)


# --------------------------------------------------------------------------
# Identity helpers for writers inside VoiceMode
# --------------------------------------------------------------------------

def caller_session() -> Optional[str]:
    """The harness session id, by converse's own precedence."""
    return (os.environ.get("VOICEMODE_SESSION_ID")
            or os.environ.get("CLAUDE_CODE_SESSION_ID")
            or os.environ.get("CLAUDE_SESSION_ID"))


def caller_agent() -> Optional[str]:
    return os.environ.get("VOICEMODE_AGENT") or os.environ.get("CLAUDE_CODE_AGENT")


def input_device_name() -> Optional[str]:
    """The OS name of the default input device, or None. Never raises.

    A label for WHERE the words came from, never WHO said them (VM-1010).
    Imports sounddevice lazily so the hook path never loads it.
    """
    try:
        import sounddevice as sd  # type: ignore
        info = sd.query_devices(kind="input")
        name = info.get("name") if isinstance(info, dict) else None
        return str(name) if name else None
    except Exception:
        return None


# --------------------------------------------------------------------------
# Reading: whole records past a seq, and where each sits in its file
# --------------------------------------------------------------------------

class _Rec:
    __slots__ = ("rec", "path", "start", "end")

    def __init__(self, rec: dict, path: Path, start: int, end: int):
        self.rec, self.path, self.start, self.end = rec, path, start, end

    @property
    def seq(self) -> int:
        return self.rec["seq"]


def _scan(path: Path, offset: int = 0) -> tuple[list[_Rec], int]:
    """Whole records in ``path`` from byte ``offset``.

    Returns the records and the byte offset just past the last whole line.
    A trailing line with no newline is a write in flight: not returned, and
    the offset stops before it, so the next read picks it up whole.
    """
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
    except OSError:
        return [], offset
    out: list[_Rec] = []
    pos = offset
    for raw in data.split(b"\n")[:-1]:
        start = pos
        pos += len(raw) + 1
        s = raw.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except (ValueError, UnicodeDecodeError):
            continue  # a torn or foreign line mid-file: skipped
        if isinstance(rec, dict) and isinstance(rec.get("seq"), int):
            out.append(_Rec(rec, path, start, pos))
    return out, pos


def read_after(seq: int, *, hint_file: Optional[str] = None, hint_offset: int = 0,
               directory: Optional[Path] = None, max_files: int = 2
               ) -> tuple[list[_Rec], Optional[tuple[Path, int]]]:
    """Records with ``seq`` greater than ``seq``, oldest first.

    ``hint_file``/``hint_offset`` (from a cursor) let the read start where
    the last one stopped instead of parsing the whole day. At most the
    newest ``max_files`` days are read: a ride-along is not an archive.
    Returns the records and (file, offset) just past the last whole line.
    """
    files = log_files(directory)
    if not files:
        return [], None
    names = [p.name for p in files]
    if hint_file in names:
        chosen = files[names.index(hint_file):]
    else:
        chosen, hint_file = files, None
    chosen = chosen[-max_files:]
    recs: list[_Rec] = []
    tail: Optional[tuple[Path, int]] = None
    for p in chosen:
        off = hint_offset if p.name == hint_file else 0
        try:
            if off > p.stat().st_size:
                off = 0  # the file was replaced under us; trust seq, not bytes
        except OSError:
            continue
        rs, end = _scan(p, off)
        recs.extend(r for r in rs if r.seq > seq)
        tail = (p, end)
    return recs, tail


# --------------------------------------------------------------------------
# The cursor: per session, the highest seq that session has been shown
# --------------------------------------------------------------------------

def cursor_dir() -> Path:
    return base_dir() / "state" / "heard-cursor"


def _session_file_name(session: str) -> str:
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in session)[:128]
    return safe.lstrip(".") or "default"


class Cursor:
    __slots__ = ("seq", "file", "offset")

    def __init__(self, seq: int, file: Optional[str] = None, offset: int = 0):
        self.seq, self.file, self.offset = seq, file, offset

    def to_json(self) -> str:
        return json.dumps(_clean({"seq": self.seq, "file": self.file,
                                  "offset": self.offset if self.file else None}))


def load_cursor(session: str, directory: Optional[Path] = None) -> Optional[Cursor]:
    path = (directory or cursor_dir()) / _session_file_name(session)
    try:
        raw = json.loads(path.read_text())
        return Cursor(int(raw["seq"]), raw.get("file"), int(raw.get("offset") or 0))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        return None  # unreadable: treated as absent, re-initialised at the end


def save_cursor(session: str, cursor: Cursor, directory: Optional[Path] = None) -> None:
    d = directory or cursor_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / _session_file_name(session)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(cursor.to_json() + "\n")
    os.replace(tmp, path)


class _SessionLock:
    """flock on ``<session>.lock``; polls up to ``timeout`` s, never blocks longer."""

    def __init__(self, session: str, timeout: float, directory: Optional[Path] = None):
        d = directory or cursor_dir()
        d.mkdir(parents=True, exist_ok=True)
        self.path = d / (_session_file_name(session) + ".lock")
        self.timeout = timeout
        self.fd: Optional[int] = None

    def __enter__(self) -> bool:
        self.fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    raise
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.02)

    def __exit__(self, *exc) -> None:
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None


def advance_cursor(session: str, seq: int, directory: Optional[Path] = None,
                   timeout: float = 2.0) -> bool:
    """Move ``session``'s cursor forward to ``seq`` (never back).

    ``listen`` calls this when it returns a turn, so the next hook does not
    print the turn the agent was just woken with. Returns False if the lock
    was not had in ``timeout`` seconds.
    """
    with _SessionLock(session, timeout, directory) as got:
        if not got:
            return False
        cur = load_cursor(session, directory)
        if cur is None:
            save_cursor(session, Cursor(seq), directory)
        elif seq > cur.seq:
            # Keep the byte hint: reading from it and filtering seq > new
            # is still right, and cheaper than a rescan.
            save_cursor(session, Cursor(seq, cur.file, cur.offset), directory)
        return True


# --------------------------------------------------------------------------
# Rendering: what a busy agent is shown on its next tool call
# --------------------------------------------------------------------------

QUIET_EVENTS = frozenset({EV_HEARTBEAT, EV_LISTEN_STARTED, EV_LISTEN_STOPPED})
# The hook shows ONLY these events; every other event (the quiet three, and
# a capture's diagnostics such as turn-discarded or stt-error, and anything
# added later) moves the cursor silently. Context-conservative by default:
# a new event is invisible to agents until someone decides it should not be.
# `exchanges tail --heard` still shows every line.
SHOWN_EVENTS = frozenset({EV_WAKE_WORD, EV_END_WORD, EV_BARGE_IN, EV_DEVICE_CHANGED,
                          EV_CALL_STARTED, EV_CALL_ENDED})
DEFAULT_BUDGET_TOKENS = 400  # Q8, ruled as recommended 03:44-03:47
_CUT_RESERVE_TOKENS = 20


def estimate_tokens(text: str) -> int:
    """Four characters a token, rounded up: an estimate, stated as one."""
    return (len(text) + 3) // 4


def _where(rec: dict) -> str:
    src = rec.get("source") or "?"
    dev = rec.get("device")
    return f"{src}/{dev}" if dev else str(src)


def _hms(rec: dict) -> str:
    ts = rec.get("ts") or ""
    return ts[11:19] if len(ts) >= 19 else "??:??:??"


def _via(rec: dict) -> str:
    via = rec.get("via")
    if not via:
        return ""
    agent = rec.get("agent")
    return f" {via}:{agent}" if agent else f" {via}"


class _Item:
    __slots__ = ("text", "first", "last")

    def __init__(self, text: Optional[str], first: int, last: int):
        self.text, self.first, self.last = text, first, last  # text None = silent


def collapse(recs: list[_Rec], session: Optional[str] = None) -> list[_Item]:
    """Records -> what to show, ordered by the seq that completed each.

    A run of partials from one source and device is subsumed by the turn
    that follows; partials with no turn yet are shown joined, as a preview.
    Quiet events and the reading session's own converse turns (it already
    has them as converse's result) are silent: they move the cursor and
    cost nothing.
    """
    pending: dict[tuple, list[dict]] = {}
    items: list[_Item] = []
    for r in recs:
        rec = r.rec
        kind = rec.get("kind")
        # via is in the key: converse writes turns with no partials, so its
        # turn must never subsume a listener's partials on the same mic.
        key = (rec.get("source"), rec.get("device"), rec.get("via"))
        if kind == PARTIAL:
            pending.setdefault(key, []).append(rec)
        elif kind == TURN:
            covers = pending.pop(key, [])
            first = covers[0]["seq"] if covers else rec["seq"]
            if rec.get("via") == "converse" and session and rec.get("session") == session:
                items.append(_Item(None, first, rec["seq"]))
            else:
                items.append(_Item(
                    f"[heard {_where(rec)} {_hms(rec)}{_via(rec)}] {rec.get('text', '')}",
                    first, rec["seq"]))
        elif kind == EVENT:
            name = rec.get("event") or "?"
            if name not in SHOWN_EVENTS:
                items.append(_Item(None, rec["seq"], rec["seq"]))
                continue
            detail = rec.get("word") or rec.get("text") or ""
            reason = rec.get("reason")
            line = f"[heard {_where(rec)} {_hms(rec)} {name}]"
            if detail:
                line += f" {detail}"
            if reason:
                line += f" ({reason})"
            items.append(_Item(line, rec["seq"], rec["seq"]))
        else:
            items.append(_Item(None, rec["seq"], rec["seq"]))  # unknown kind: skipped
    for key, parts in pending.items():
        first = parts[0]
        joined = " ".join(p.get("text", "").strip() for p in parts).strip()
        items.append(_Item(
            f"[heard {_where(first)} {_hms(first)} partial] {joined} …",
            first["seq"], parts[-1]["seq"]))
    items.sort(key=lambda it: it.last)
    return items


def render(items: list[_Item], *, budget_tokens: int = DEFAULT_BUDGET_TOKENS,
           max_lines: Optional[int] = None, file_name: str = "the heard log"
           ) -> tuple[str, Optional[int]]:
    """Fit ``items`` to the budget, oldest first.

    Returns the text (empty when there is nothing to show) and the seq the
    cursor may move to (None when there were no items at all). On a cut the
    last line is ``[heard] +k more, seq a-b`` and the cursor stops at the
    last item printed. The first shown line is always printed, cut short
    if it alone is over budget, so one long turn cannot jam the cursor.
    """
    if not items:
        return "", None
    out: list[str] = []
    used = 0
    cursor = None
    shown = 0
    limit = max(budget_tokens - _CUT_RESERVE_TOKENS, 1)
    for i, it in enumerate(items):
        if it.text is None:
            cursor = it.last
            continue
        cost = estimate_tokens(it.text) + 1
        over_lines = max_lines is not None and shown >= max_lines
        if over_lines or (shown and used + cost > limit):
            rest = [x for x in items[i:] if x.text is not None]
            a = items[i].first if cursor is None else cursor + 1
            b = max(x.last for x in items[i:])
            out.append(f"[heard] +{len(rest)} more, seq {a}-{b}")
            return "\n".join(out), cursor
        text = it.text
        if cost > limit:
            keep = max(limit * 4 - 80, 40)
            text = (f"{text[:keep]} … (+{len(text) - keep} chars; whole line: "
                    f"seq {it.last} in {file_name})")
            cost = estimate_tokens(text) + 1
        out.append(text)
        used += cost
        shown += 1
        cursor = it.last
    return "\n".join(out), cursor


# --------------------------------------------------------------------------
# Following: every line, for a human (`voicemode exchanges tail --heard`)
# --------------------------------------------------------------------------

def format_record(rec: dict) -> str:
    """One log line, whole: every kind, quiet events included (this is the
    diagnostic view; the hook is the context-conservative one)."""
    kind = rec.get("kind") or "?"
    head = f"#{rec.get('seq', '?')} {_hms(rec)} {kind:<7} {_where(rec)}{_via(rec)}"
    if kind == EVENT:
        body = " ".join(str(x) for x in (rec.get("event"), rec.get("word") or rec.get("text"),
                                         f"({rec['reason']})" if rec.get("reason") else None) if x)
    else:
        body = rec.get("text", "")
        if kind == TURN and rec.get("detector"):
            body += f"  [{rec['detector']}]"
    return f"{head}  {body}"


def follow(*, backlog: int = 10, after_seq: Optional[int] = None, poll: float = 0.5,
           directory: Optional[Path] = None, stop=None) -> Iterable[dict]:
    """Yield records as they are written, across midnight, oldest first.

    Starts with the last ``backlog`` records (or everything after
    ``after_seq``), then polls every ``poll`` seconds. ``stop()`` returning
    True ends it (tests); otherwise it runs until interrupted.
    """
    if after_seq is None:
        recs, tail = read_after(-1, directory=directory, max_files=1)
        for r in recs[-backlog:] if backlog > 0 else []:
            yield r.rec
        seq = recs[-1].seq if recs else last_seq(directory)
    else:
        recs, tail = [], None
        seq = after_seq
    hint = tail
    while True:
        recs, tail = read_after(seq, hint_file=hint[0].name if hint else None,
                                hint_offset=hint[1] if hint else 0, directory=directory)
        for r in recs:
            yield r.rec
            seq = r.seq
        if tail:
            hint = tail
        if stop is not None and stop():
            return
        time.sleep(poll)


# --------------------------------------------------------------------------
# The ride-along hook
# --------------------------------------------------------------------------

def _env_int(name: str, default: Optional[int]) -> Optional[int]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def hook_disabled() -> bool:
    return os.environ.get("VOICEMODE_HEARD_HOOK", "").strip().lower() in (
        "0", "off", "false", "no")


def _init_cursor(session: str, log_directory: Optional[Path],
                 cursor_directory: Optional[Path]) -> Cursor:
    """A session with no cursor starts at the end of the log."""
    files = log_files(log_directory)
    if files:
        recs, tail = read_after(-1, hint_file=files[-1].name, directory=log_directory,
                                max_files=1)
        seq = recs[-1].seq if recs else last_seq(log_directory)
        cur = Cursor(seq, tail[0].name if tail else None, tail[1] if tail else 0)
    else:
        cur = Cursor(0)
    save_cursor(session, cur, cursor_directory)
    return cur


def pending(session: str, *, log_directory: Optional[Path] = None,
            cursor_directory: Optional[Path] = None, lock_timeout: float = 1.0
            ) -> Optional[list[dict]]:
    """Records past ``session``'s cursor, oldest first; the cursor does not move.

    For a waiter (``pager listen``'s shape): poll this, decide whether an
    aged turn is there, then ``take()``. A session with no cursor gets one
    at the end of the log, and ``[]``. None if the lock was not had.
    """
    with _SessionLock(session, lock_timeout, cursor_directory) as got:
        if not got:
            return None
        cur = load_cursor(session, cursor_directory)
        if cur is None:
            _init_cursor(session, log_directory, cursor_directory)
            return []
        recs, _ = read_after(cur.seq, hint_file=cur.file, hint_offset=cur.offset,
                             directory=log_directory)
        return [r.rec for r in recs]


def take(session: str, *, budget_tokens: Optional[int] = None,
         max_lines: Optional[int] = None, log_directory: Optional[Path] = None,
         cursor_directory: Optional[Path] = None, lock_timeout: float = 1.0
         ) -> tuple[str, Optional[int]]:
    """Render what ``session`` has not been shown, and advance its cursor.

    Exactly what the hook prints (collapse, budget, cut line), as plain
    text, plus the cursor's new seq. ``("", seq)`` when there is nothing
    to show; ``("", None)`` when the lock was not had. A waiter that wakes
    an idle agent prints this and exits, so the hook does not repeat it.
    """
    budget = budget_tokens if budget_tokens is not None else _env_int(
        "VOICEMODE_HEARD_BUDGET", DEFAULT_BUDGET_TOKENS)
    if max_lines is None:
        max_lines = _env_int("VOICEMODE_HEARD_MAX_LINES", None)
    with _SessionLock(session, lock_timeout, cursor_directory) as got:
        if not got:
            return "", None
        cur = load_cursor(session, cursor_directory)
        if cur is None:
            cur = _init_cursor(session, log_directory, cursor_directory)
            return "", cur.seq
        recs, tail = read_after(cur.seq, hint_file=cur.file, hint_offset=cur.offset,
                                directory=log_directory)
        if not recs:
            if tail and (tail[0].name != cur.file or tail[1] != cur.offset):
                save_cursor(session, Cursor(cur.seq, tail[0].name, tail[1]), cursor_directory)
            return "", cur.seq
        items = collapse(recs, session)
        text, new_seq = render(items, budget_tokens=budget, max_lines=max_lines,
                               file_name=recs[-1].path.name)
        if new_seq is not None and new_seq > cur.seq:
            if new_seq == recs[-1].seq and tail:
                where = (tail[0].name, tail[1])
            else:
                at = next((r for r in recs if r.seq == new_seq), None)
                where = (at.path.name, at.end) if at else (None, 0)
            save_cursor(session, Cursor(new_seq, where[0], where[1]), cursor_directory)
            return text, new_seq
        return text, cur.seq


def run_hook(stdin_text: str, *, budget_tokens: Optional[int] = None,
             max_lines: Optional[int] = None, log_directory: Optional[Path] = None,
             cursor_directory: Optional[Path] = None, lock_timeout: float = 1.0
             ) -> Optional[str]:
    """One hook run. Returns the JSON Claude Code reads, or None for silence.

    The session is the hook input's ``session_id`` (else the environment's).
    A session with no cursor starts at the end of the log and is shown
    nothing: a new session is not handed what was said before it existed.
    If another reader of the same session holds the lock, this one is
    silent (the holder is printing the same lines).
    """
    try:
        data = json.loads(stdin_text) if stdin_text.strip() else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    session = str(data.get("session_id") or caller_session() or "default")
    event_name = str(data.get("hook_event_name") or "PostToolUse")
    text, _ = take(session, budget_tokens=budget_tokens, max_lines=max_lines,
                   log_directory=log_directory, cursor_directory=cursor_directory,
                   lock_timeout=lock_timeout)
    if not text:
        return None
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": event_name, "additionalContext": text}}, ensure_ascii=False)


# --------------------------------------------------------------------------
# Script entry: `voicemode-heard-hook hook` (installed copy of this file)
# --------------------------------------------------------------------------

def _usage() -> str:
    return ("usage: heard.py hook [--budget TOKENS] [--max-lines N]   (reads hook JSON on stdin)\n"
            "       heard.py write partial|turn TEXT [--source S] [--device D] [--detector D]\n"
            "       heard.py write event NAME [--source S] [--device D] [--text T]\n"
            "       heard.py last-seq\n")


def _opts(argv: list[str]) -> tuple[list[str], dict[str, str]]:
    pos: list[str] = []
    opts: dict[str, str] = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--") and i + 1 < len(argv):
            opts[a[2:].replace("-", "_")] = argv[i + 1]
            i += 2
        else:
            pos.append(a)
            i += 1
    return pos, opts


def main(argv: Optional[list[str]] = None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    verb = argv.pop(0) if argv else "hook"
    pos, opts = _opts(argv)
    if verb == "hook":
        if hook_disabled():
            return 0
        stdin_text = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
        try:
            out = run_hook(stdin_text,
                           budget_tokens=int(opts["budget"]) if "budget" in opts else None,
                           max_lines=int(opts["max_lines"]) if "max_lines" in opts else None)
        except Exception as e:
            # Fail LOUD, but with 1, never 2. Measured 04:11 Thu 2026-09-24
            # (claude -p, 2.1.280): exit 1 on PostToolUse/PostToolBatch shows
            # as a hook error and the agent carries on; exit 2 STOPS the
            # agent's turn after the tool. A zero here would claim a quiet
            # room while the ride-along is broken (Charter 2).
            sys.stderr.write(f"[heard] the hook failed: {type(e).__name__}: {e}\n")
            return 1
        if out:
            print(out)
        return 0
    if verb == "write":
        if len(pos) < 2:
            sys.stderr.write(_usage())
            return 1
        kind, text = pos[0], pos[1]
        kw: dict[str, Any] = {k: v for k, v in opts.items()}
        if kind == EVENT:
            rec = event(text, **kw)
        else:
            rec = append(kind, text=text, **kw)
        print(json.dumps(rec, ensure_ascii=False))
        return 0
    if verb == "last-seq":
        print(last_seq())
        return 0
    sys.stderr.write(_usage())
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

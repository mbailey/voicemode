"""The queue is a maildir: new = to speak, cur = done.

Mike, voice 02:55 Sat 2026-09-26 (via Cora): the mouth's queue as a
maildir. Pip's design <1790355365.58952.12604@m5.session-mail>; Mike,
03:24-03:26: *"we may as well drop the files as mail, maybe using mail
drop ... Yes"*.

    new/   lines to speak, one mail each. Every way in lands here:
           `mouth say` drops one (tmp/ then rename, about 1 ms), and
           postfix delivers mail to mouth@<host> (about 250 ms).
    cur/   done, each flagged in its name (maildir ``:2,FLAGS``): S spoken
           (all or part), T not spoken (retracted, replaced, stopped,
           refused, an error), P passed (expired, or stale). A line
           playing now sits in cur/ with no flag yet.
    tmp/   being written.

Where: ``$VOICEMODE_MOUTH_MAILBOX``; else, for the live mouth dir, the
mouth's own mailbox ``~/.mail/agents/mouth`` (the box is the queue and the
log: Mike, 21:52 Thu, "the single source of truth"); else
``<mouth dir>/box``, so a test or a dry run never touches the live one.

Order, a playlist (Mike, 03:07-03:12): ``X-Mouth-Priority`` sorts first,
lower plays sooner: ``now`` (-1, and it cuts the line playing), ``next``
(0), a number (10, 20, 30...), none (50: the back of the list). Within a
priority, arrival order: ``X-Mouth-Order`` (nanoseconds), else the file's
mtime. ``Importance: high`` is ``next``.

Replace is a supersede: a mail whose ``Supersedes:`` names a line still in
new/ takes that line's place (its priority, order and utt); the older is
filed T when the newer is taken. An EMPTY body retracts: both are filed T
at once. A supersede of a line already gone is news, played on its own; an
empty one is filed T, and cuts the line if it is playing. Nothing is ever
edited in place.

A mail from outside (no ``X-Mouth-Raw: 1``) is spoken the way ``mouth
mail`` spoke it: the plain body un-markdowned, or the Subject; who may
speak is the same From check (``allowed``).
"""

from __future__ import annotations

import email
import email.policy
import email.utils
import hashlib
import json
import os
import re
import socket
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from .paths import default_mouth_dir, mouth_dir
from .voices import default_voice

DEFAULT_RANK = 50.0
RANKS = {"now": -1.0, "next": 0.0}
INTERESTS = ("high", "normal", "low", "zero")
_PANS = {"left": -1.0, "right": 1.0, "both": None}

#: item key -> header. Anything else a line carries rides in X-Mouth-Extra (JSON).
FIELDS = {
    "utt": "X-Mouth-Utt", "voice": "X-Mouth-Voice", "speed": "X-Mouth-Speed",
    "backend": "X-Mouth-Backend", "device": "X-Mouth-Device", "pan": "X-Mouth-Pan",
    "priority": "X-Mouth-Priority", "hold": "X-Mouth-When", "interest": "X-Mouth-Interest",
    "expires_s": "X-Mouth-Expires", "file": "X-Mouth-File", "start": "X-Mouth-Start",
    "end": "X-Mouth-End", "log_dir": "X-Mouth-Log-Dir", "mail_log": "X-Mouth-Mail-Log",
    "agent": "X-Mouth-Agent", "session": "X-Session-From", "resume_of": "X-Mouth-Resume-Of",
}
#: Carried by the mail itself (body, Message-ID, From, order), never as extras.
_OWN = ("text", "requested_t", "requested_ts", "expires_t", "wait", "mail_id", "mail_from")


# -- where, and the maildir moves ---------------------------------------------

def box_dir(d: Optional[Path] = None) -> Path:
    env = os.environ.get("VOICEMODE_MOUTH_MAILBOX")
    if env:
        return Path(env).expanduser()
    d = Path(d or mouth_dir()).expanduser()
    if os.path.abspath(d) == os.path.abspath(default_mouth_dir()):
        return Path.home() / ".mail" / "agents" / "mouth"
    return d / "box"


def ensure(bx: Path) -> Path:
    for sub in ("tmp", "new", "cur"):
        (bx / sub).mkdir(parents=True, exist_ok=True)
    return bx


def _host() -> str:
    return socket.gethostname().split(".")[0].lower()


def _base(name: str) -> str:
    return name.split(":2,")[0]


def file_to(path: Path, flags: str) -> Optional[Path]:
    """Move a mail from new/ (or a taken one in cur/) to cur/NAME:2,FLAGS. None if it is gone."""
    dest = path.parent.parent / "cur" / f"{_base(path.name)}:2,{''.join(sorted(flags))}"
    try:
        path.rename(dest)
    except FileNotFoundError:
        return None
    return dest


# -- markdown to speech, and who may speak (from inbox.py) --------------------

def speakable(text: str) -> str:
    """Markdown to something a voice can read aloud."""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)          # [text](url) -> text
    t = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", t)                 # `code` -> code
    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t)                    # **bold**
    t = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", t)                  # # heads
    t = re.sub(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", "", t)           # list bullets
    t = re.sub(r"(?m)^\s*>\s?", "", t)                           # > quotes
    return re.sub(r"[ \t]+", " ", t).strip()


def allowed(sender: str) -> bool:
    """A From on this host (``@<host>``, ``@<host>.<tailnet>``) or in $VOICEMODE_MOUTH_MAIL_ALLOW."""
    s = sender.lower()
    extra = [x.strip().lower() for x in os.environ.get("VOICEMODE_MOUTH_MAIL_ALLOW", "").split(",") if x.strip()]
    if any(s == x or (x.startswith("@") and s.endswith(x)) for x in extra):
        return True
    at = s[s.rfind("@"):] if "@" in s else ""
    host = _host()
    return at == f"@{host}" or at.startswith(f"@{host}.")


# -- a line as a mail, and back ------------------------------------------------

def _subject(text: str) -> str:
    line = " ".join((text or "").split())
    return line if len(line) <= 69 else line[:68] + "…"


def drop(bx: Path, item: dict, *, supersedes: Optional[str] = None) -> Path:
    """Write ITEM into BX/new as a mail: tmp/, then one rename. Sets ``item['mail_id']``."""
    ensure(bx)
    host = _host()
    order = time.time_ns()
    mid = f"<{order}.{item['utt']}@{host}.mouth>"
    m = EmailMessage()
    m["From"] = f"{item.get('agent') or 'mouth'}@{host}"
    m["To"] = f"mouth@{host}"
    m["Date"] = email.utils.formatdate(item["requested_t"], localtime=True)
    m["Subject"] = _subject(item["text"])
    m["Message-ID"] = mid
    if supersedes:
        m["Supersedes"] = supersedes
        m["In-Reply-To"] = supersedes
        m["References"] = supersedes
    m["X-Mouth-Raw"] = "1"
    m["X-Mouth-Order"] = str(order)
    m["X-Mouth-Requested"] = repr(float(item["requested_t"]))
    if item.get("wait"):
        m["X-Mouth-Wait"] = "1"
    for k, h in FIELDS.items():
        v = item.get(k)
        if v is not None:
            m[h] = str(v)
    extras = {k: v for k, v in item.items()
              if k not in FIELDS and k not in _OWN and not k.startswith("_") and v is not None}
    if extras:
        m["X-Mouth-Extra"] = json.dumps(extras, ensure_ascii=True, separators=(",", ":"))
    m.set_content(item["text"] + "\n")  # read() takes exactly this newline back off
    name = f"{order}.{item['utt']}.{host}"
    tmp = bx / "tmp" / name
    tmp.write_bytes(bytes(m))
    dest = bx / "new" / name
    tmp.rename(dest)
    item["mail_id"] = mid
    return dest


def _float(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _pan(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    v = v.strip().lower()
    if v in _PANS:
        return _PANS[v]
    p = _float(v)
    return p if p is not None and -1.0 <= p <= 1.0 else None


def _body(msg) -> str:
    part = msg.get_body(preferencelist=("plain",))
    return part.get_content() if part is not None else ""


def read(path: Path, d: Optional[Path] = None) -> Optional[dict]:
    """One mail in new/ as a line the player can speak (``_``-keys: the mail's own
    facts). None if it has gone meanwhile."""
    try:
        raw = path.read_bytes()
        mtime_ns = path.stat().st_mtime_ns
    except FileNotFoundError:
        return None
    msg = email.message_from_bytes(raw, policy=email.policy.default)

    def h(k: str) -> Optional[str]:
        v = msg.get(k)
        return str(v).strip() if v is not None else None

    mid = h("Message-ID") or f"<{path.name}@mouth>"
    sender = email.utils.parseaddr(h("From") or "")[1]
    body = _body(msg)
    is_raw = h("X-Mouth-Raw") == "1"
    if is_raw:
        text = body[:-1] if body.endswith("\n") else body
    else:
        text = speakable(body.strip()) or speakable(h("Subject") or "")
    try:
        own_order = int(h("X-Mouth-Order") or "")
    except ValueError:
        own_order = mtime_ns
    requested_t = _float(h("X-Mouth-Requested")) or own_order / 1e9

    pri = (h("X-Mouth-Priority") or "").lower() or \
        ("next" if (h("Importance") or "").lower() == "high" else "")
    priority: object = None
    rank = DEFAULT_RANK
    if pri in RANKS:
        priority, rank = pri, RANKS[pri]
    elif _float(pri) is not None:
        rank = _float(pri)
        priority = int(rank) if rank == int(rank) else rank
    try:
        extras = json.loads(h("X-Mouth-Extra") or "{}")
    except ValueError:
        extras = {}
    expires_s = _float(h("X-Mouth-Expires"))
    want = (h("X-Mouth-Interest") or "").lower()
    item = {
        "utt": h("X-Mouth-Utt") or "m" + hashlib.sha1(mid.encode()).hexdigest()[:11],
        "text": text,
        "voice": h("X-Mouth-Voice") or default_voice(d)[0],
        "speed": _float(h("X-Mouth-Speed")),
        "backend": h("X-Mouth-Backend") or os.environ.get("VOICEMODE_MOUTH_BACKEND") or "auto",
        "device": h("X-Mouth-Device") or os.environ.get("VOICEMODE_MOUTH_DEVICE"),
        "pan": _pan(h("X-Mouth-Pan") or h("X-Mouth-Channel")),
        "requested_t": requested_t,
        "requested_ts": datetime.fromtimestamp(requested_t).astimezone().isoformat(timespec="milliseconds"),
        "agent": h("X-Mouth-Agent") or (sender.split("@")[0] if sender else None),
        "session": h("X-Session-From"),
        "log_dir": h("X-Mouth-Log-Dir") or (None if is_raw else os.environ.get("VOICEMODE_MOUTH_LOG_DIR")),
        "wait": h("X-Mouth-Wait") == "1",
        "priority": priority,
        "hold": "turn-end" if (h("X-Mouth-When") or "").lower() == "turn-end" else None,
        "interest": want if want in INTERESTS else None,
        "expires_s": expires_s,
        "expires_t": requested_t + expires_s if expires_s is not None else None,
        "file": h("X-Mouth-File"),
        "start": _float(h("X-Mouth-Start")),
        "end": _float(h("X-Mouth-End")),
        "resume_of": h("X-Mouth-Resume-Of"),
        "mail_id": mid,
        "mail_from": sender or None,
    }
    if is_raw:
        item["mail_log"] = h("X-Mouth-Mail-Log")
    else:  # a mail from outside threads its log under itself (maillog)
        from . import maillog

        item["mail_log"] = maillog.box_from_env()
        item["log_root"] = mid
    item.update(extras)
    if item["file"]:
        item["backend"] = "file"
        if not is_raw:
            s, e = item["start"], item["end"]
            span = f" {s or 0:g}-{e:g}s" if e is not None else (f" from {s:g}s" if s else "")
            item["text"] = f"[sound {Path(item['file']).name}{span}]"
    sup = h("Supersedes")
    item.update(_path=path, _name=path.name, _sup=sup, _raw=is_raw,
                _retract=bool(sup) and not body.strip() and not item["file"],
                _allowed=allowed(sender), _rank=rank, _order=own_order, _own_order=own_order,
                _chain=[])
    return item


def public(item: dict) -> dict:
    """The line without the mail's ``_`` facts: what playing.json and done/ hold."""
    return {k: v for k, v in item.items() if not k.startswith("_")}


# -- the queue: new/, parsed once per file, in play order ---------------------

class Queue:
    """The lines in a mouth's maildir, supersedes resolved, in play order.

    ``lines(act=True)`` also files what needs no player: a refused sender,
    a retract (and what it retracts), and it cuts a playing line a retract
    names. Only the player acts; readers (status, prefetch) pass False.
    """

    def __init__(self, d: Optional[Path] = None) -> None:
        self.d = Path(d or mouth_dir())
        self.bx = box_dir(self.d)
        self._cache: dict = {}
        self._acked: set = set()

    @property
    def new(self) -> Path:
        return self.bx / "new"

    def entries(self) -> list:
        try:
            names = sorted(n for n in os.listdir(self.new) if not n.startswith("."))
        except FileNotFoundError:
            return []
        live = set(names)
        for n in [n for n in self._cache if n not in live]:
            del self._cache[n]
        out = []
        for n in names:
            e = self._cache.get(n)
            if e is None:
                e = read(self.new / n, self.d)
                if e is None:
                    continue
                self._cache[n] = e
            out.append(e)
        return out

    def lines(self, act: bool = False, playing: Optional[dict] = None) -> list:
        from .player import _done, said_unplayed

        eff: dict = {}
        for e in sorted(self.entries(), key=lambda e: (e["_own_order"], e["_name"])):
            if not e["_allowed"]:
                if act and file_to(e["_path"], "T"):
                    print(json.dumps({"refused": e["mail_from"], "mail_id": e["mail_id"]}), flush=True)
                continue
            if act and not e["_raw"] and e["mail_id"] not in self._acked:
                self._acked.add(e["mail_id"])  # a mail from outside: say it was queued, in its thread
                from . import maillog

                maillog.entry(e, "queued", {k: e.get(k) for k in (
                    "utt", "text", "voice", "device", "pan", "priority", "hold", "expires_t",
                    "agent", "session", "requested_ts", "file", "mail_id")})
            x = dict(e)
            t = eff.get(e["_sup"]) if e["_sup"] else None
            if t is not None and not t.get("_gone"):
                if e["_retract"]:
                    t["_gone"], x["_gone"] = "retracted", "retract"
                    if act:
                        for p in [t, *t["_chain"]]:
                            file_to(p["_path"], "T")
                        file_to(e["_path"], "T")
                        _done(self.d, public(t), said_unplayed(public(t), "retracted"))
                else:
                    t["_gone"] = "replaced"
                    x.update(utt=t["utt"], _rank=t["_rank"] if e["priority"] is None else e["_rank"],
                             _order=t["_order"], requested_t=t["requested_t"],
                             requested_ts=t["requested_ts"],
                             amended_from=t.get("amended_from") or t["text"],
                             _chain=[*t["_chain"], t])
            elif e["_sup"] and e["_retract"]:
                x["_gone"] = "retract"
                if act:
                    if playing and playing.get("mail_id") == e["_sup"]:
                        from . import _stop_file

                        _stop_file(self.d, {"t": time.time(), "reason": "retracted", "flush": False,
                                            "utt": playing["utt"]})
                    file_to(e["_path"], "T")
            eff[e["mail_id"]] = x
        out = [x for x in eff.values() if not x.get("_gone")]
        return sorted(out, key=lambda x: (x["_rank"], x["_order"], x["_name"]))

    def find(self, utt: str) -> Optional[dict]:
        return next((x for x in self.lines() if x["utt"] == utt), None)

    def take(self, x: dict) -> Optional[Path]:
        """Claim X to play: new/ -> cur/NAME:2, (no flag yet); what it replaced -> T."""
        dest = self.bx / "cur" / f"{_base(x['_name'])}:2,"
        try:
            x["_path"].rename(dest)
        except FileNotFoundError:
            return None
        for p in x["_chain"]:
            file_to(p["_path"], "T")
        return dest

    def drop_line(self, x: dict, flags: str) -> bool:
        """File a line (and what it replaced) without playing it. False if it had gone."""
        ok = file_to(x["_path"], flags) is not None
        for p in x["_chain"]:
            file_to(p["_path"], "T")
        return ok

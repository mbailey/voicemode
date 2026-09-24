"""Mail feeds mouth: a mail to ``mouth@m5`` becomes a queued line.

Ruled by Mike, voice 21:40 Thu 2026-09-24 ("mail feeds mouth", slipbox
convention 515). The mail is the transport; the mouth's own queue, player
and heard-log lines are unchanged. ``mouth say`` stays the direct path for
fast openers.

How a mail maps:

- **the text:** the plain-text body, lightly un-markdowned (``**``,
  backticks, ``#`` heads, list bullets, ``[text](url)`` -> text). An empty
  body speaks the Subject.
- **amend:** ``Supersedes: <id>`` of a mail whose line hasn't played yet
  rewrites it in place. If that line has already been spoken, the new text
  is queued as a line of its own: a correction is still news.
- **retract:** ``Supersedes: <id>`` with an EMPTY body. The line is dropped,
  or cut if it's playing.
- **priority:** ``Importance: high`` -> ``next``;
  ``X-Mouth-Priority: next|now`` says so exactly.
- **a sound:** ``X-Mouth-File`` (path or URL), with optional
  ``X-Mouth-Start`` / ``X-Mouth-End`` seconds.
- **per-line options:** ``X-Mouth-Voice``, ``X-Mouth-Speed``,
  ``X-Mouth-Device``, ``X-Mouth-Channel`` (left|right|both) or
  ``X-Mouth-Pan``. Anything unset falls back to the watcher's
  ``$VOICEMODE_MOUTH_*`` environment.
- **who:** ``agent`` is the From's local part; ``session`` is
  ``X-Session-From``. ``mail_id`` goes on the saying/said lines.

**Who may speak:** only a From on this host (``@<host>`` or
``@<host>.<tailnet>``) or one listed in ``$VOICEMODE_MOUTH_MAIL_ALLOW``
(comma-separated addresses or ``@domains``). This is a From check, which a
forger can defeat; verifying ``X-Session-Signature`` is the follow-up. A
refused mail is filed to ``cur/`` and never spoken.

A mail is taken from ``new/`` and filed to ``cur/`` (seen) once it has been
acted on, so a restart never speaks it twice.
"""

from __future__ import annotations

import email
import email.policy
import email.utils
import json
import os
import re
import socket
import sys
import time
from pathlib import Path
from typing import Optional

from . import amend, play, retract, say
from .paths import mouth_dir


def mail_box() -> Path:
    env = os.environ.get("VOICEMODE_MOUTH_MAILBOX")
    return Path(env).expanduser() if env else Path.home() / ".mail" / "agents" / "mouth"


def speakable(text: str) -> str:
    """Markdown to something a voice can read aloud."""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)          # [text](url) -> text
    t = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", t)                 # `code` -> code
    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t)                    # **bold**
    t = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", t)                  # # heads
    t = re.sub(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", "", t)           # list bullets
    t = re.sub(r"(?m)^\s*>\s?", "", t)                           # > quotes
    return re.sub(r"[ \t]+", " ", t).strip()


def _host_domains() -> tuple[str, ...]:
    host = socket.gethostname().split(".")[0].lower()
    return (f"@{host}", f"@{host}.")


def allowed(sender: str) -> bool:
    s = sender.lower()
    extra = [x.strip().lower() for x in os.environ.get("VOICEMODE_MOUTH_MAIL_ALLOW", "").split(",") if x.strip()]
    if any(s == x or (x.startswith("@") and s.endswith(x)) for x in extra):
        return True
    at = s[s.rfind("@"):] if "@" in s else ""
    here, dotted = _host_domains()
    return at == here or at.startswith(dotted)


def _index_path(d: Path) -> Path:
    return d / "mail-index.jsonl"


def _remember(d: Path, mail_id: str, utt: str) -> None:
    with open(_index_path(d), "a") as f:
        f.write(json.dumps({"mail_id": mail_id, "utt": utt}) + "\n")


def _utt_for(d: Path, mail_id: str) -> Optional[str]:
    try:
        for line in reversed(_index_path(d).read_text().splitlines()):
            rec = json.loads(line)
            if rec.get("mail_id") == mail_id:
                return rec["utt"]
    except FileNotFoundError:
        pass
    return None


def _body(msg) -> str:
    part = msg.get_body(preferencelist=("plain",))
    return (part.get_content() if part is not None else "").strip()


def _float(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def handle(path: Path, d: Optional[Path] = None) -> dict:
    """Act on one mail file. Returns what was done (never raises for a bad mail)."""
    d = d or mouth_dir()
    msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    sender = email.utils.parseaddr(str(msg.get("From", "")))[1]
    mail_id = str(msg.get("Message-ID", "")).strip()
    if not allowed(sender):
        return {"action": "refused", "from": sender, "mail_id": mail_id}
    body = _body(msg)
    text = speakable(body) if body else speakable(str(msg.get("Subject", "")))
    sup = str(msg.get("Supersedes", "")).strip()
    h = lambda k: (str(msg.get(k)).strip() if msg.get(k) is not None else None)  # noqa: E731
    pri = (h("X-Mouth-Priority") or "").lower() or ("next" if (h("Importance") or "").lower() == "high" else None)
    opts = dict(voice=h("X-Mouth-Voice"), speed=_float(h("X-Mouth-Speed")), device=h("X-Mouth-Device"),
                pan=(h("X-Mouth-Channel") or _float(h("X-Mouth-Pan"))),
                priority=pri if pri in ("next", "now") else None, d=d)
    tag = {"mail_id": mail_id, "mail_from": sender}
    agent = sender.split("@")[0] or None
    session = h("X-Session-From")

    if sup:
        old = _utt_for(d, sup)
        if old and not body:
            try:
                retract(old, d=d)
                return {"action": "retracted", "utt": old, **tag}
            except ValueError:
                return {"action": "retract-too-late", "utt": old, **tag}
        if old:
            try:
                amend(old, text, d=d)
                _remember(d, mail_id, old)
                return {"action": "amended", "utt": old, **tag}
            except ValueError:
                pass  # already spoken: the correction is queued as news
        elif not body:
            return {"action": "retract-unknown", "supersedes": sup, **tag}

    try:
        with _as(agent, session):
            if h("X-Mouth-File"):
                item = play(h("X-Mouth-File"), start=_float(h("X-Mouth-Start")),
                            end=_float(h("X-Mouth-End")), extra_tag=tag, **opts)
            else:
                if not text:
                    return {"action": "empty", **tag}
                item = say(text, extra=tag, **opts)
    except (ValueError, TimeoutError) as e:
        return {"action": "error", "error": str(e), **tag}
    _remember(d, mail_id, item["utt"])
    return {"action": "queued", "utt": item["utt"], "priority": opts["priority"], **tag}


class _as:
    """Say it as the sender: agent and session come from the mail, not the watcher."""

    def __init__(self, agent: Optional[str], session: Optional[str]) -> None:
        self.env = {"VOICEMODE_AGENT": agent, "VOICEMODE_SESSION_ID": session}
        self.saved: dict = {}

    def __enter__(self):
        for k, v in self.env.items():
            self.saved[k] = os.environ.get(k)
            if v:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _file_seen(path: Path) -> None:
    cur = path.parent.parent / "cur"
    cur.mkdir(exist_ok=True)
    name = path.name if ":2," in path.name else f"{path.name}:2,S"
    path.rename(cur / name)


def process_new(box: Optional[Path] = None, d: Optional[Path] = None) -> list[dict]:
    """Act on every mail in new/, oldest first; file each to cur/. One pass."""
    box = box or mail_box()
    out = []
    try:
        names = sorted(os.listdir(box / "new"))
    except FileNotFoundError:
        return out
    for name in names:
        if name.startswith("."):
            continue
        p = box / "new" / name
        try:
            r = handle(p, d)
        except Exception as e:  # noqa: BLE001 - one bad mail must not stop the watcher
            r = {"action": "error", "error": f"{type(e).__name__}: {e}"[:300], "file": name}
        try:
            _file_seen(p)
        except FileNotFoundError:
            pass
        out.append(r)
    return out


def watch(box: Optional[Path] = None, poll_s: float = 0.05) -> int:
    """Forever: take mail from new/ as it lands (about 50 ms after delivery)."""
    box = box or mail_box()
    (box / "new").mkdir(parents=True, exist_ok=True)
    print(json.dumps({"watching": str(box), "mouth": str(mouth_dir())}), flush=True)
    while True:
        for r in process_new(box):
            print(json.dumps({"t": time.strftime("%H:%M:%S"), **r}), flush=True)
        time.sleep(poll_s)


if __name__ == "__main__":
    sys.exit(watch())

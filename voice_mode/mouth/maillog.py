"""The mouth's mailbox is its own log: syslog, in message form.

Mike, voice 21:52-21:54 Thu 2026-09-24 (relayed by Cora
<1790250869.45008.5357@m5.session-mail>): "a mailbox basically for the log
... it reads its own mailbox and it writes to its own mailbox. And that's
the single source of truth ... a bit like syslog but using the message
format."

Opt-in while he rules on the details: ``$VOICEMODE_MOUTH_MAIL_LOG`` is ``1``
(the mouth's box, ``~/.mail/agents/mouth``) or a maildir path. ``mouth mail``
turns it on for its own box. The heard-log lines are written as well.

Every utterance is a thread:

- ``queued``: the root for a direct ``mouth say``, or a reply to the
  request mail when the line came by mail
- ``saying``: first frame (``gen_s``, device), a reply in the thread
- ``said``: the end (``played_s``, ``cut``, ``reason``, ``underrun_s``,
  the text as played)

Service entries (``enabled``, ``disabled``) stand alone. Entries are written
straight into the box's ``cur/``, already seen (the maildir tmp -> rename
protocol), so the watcher never takes one for a request and no SMTP loop is
possible. On a central mouth server they would travel by SMTP instead.
"""

from __future__ import annotations

import email.utils
import json
import os
import socket
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

LOG_VAR = "VOICEMODE_MOUTH_MAIL_LOG"


def box_from_env() -> Optional[str]:
    v = os.environ.get(LOG_VAR, "").strip()
    if not v or v == "0":
        return None
    if v == "1":
        return str(Path.home() / ".mail" / "agents" / "mouth")
    return str(Path(v).expanduser())


def _host() -> str:
    return socket.gethostname().split(".")[0].lower()


def _q(text: str, n: int) -> str:
    t = " ".join((text or "").split())
    return f'"{t[:n]}…"' if len(t) > n else f'"{t}"'


def subject(kind: str, rec: dict) -> str:
    utt = rec.get("utt", "")
    if kind == "queued":
        pri = f" {rec['priority']}" if rec.get("priority") else ""
        return f"queued{pri} {utt}: {_q(rec.get('text', ''), 60)}"
    if kind == "saying":
        return f"saying {utt} on {rec.get('device', '?')}, gen {rec.get('gen_s') or 0:.2f}s"
    if kind == "said":
        return (f"said {rec.get('reason', '?')} {rec.get('played_s') or 0:.1f}s: "
                f"{_q(rec.get('text_played_est', ''), 50)}")
    return f"{kind}: {rec.get('detail') or ''}".rstrip(": ")


def write(box: str | Path, kind: str, rec: dict, *, in_reply_to: Optional[str] = None) -> str:
    """Deliver one log entry into BOX's cur/ (seen). Returns its Message-ID."""
    box = Path(box)
    host = _host()
    mid = f"<{time.time_ns()}.{rec.get('utt') or kind}.{kind}@{host}.mouth>"
    m = EmailMessage()
    m["From"] = f"mouth@{host}"
    m["To"] = f"mouth@{host}"
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Subject"] = subject(kind, rec)
    m["Message-ID"] = mid
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = in_reply_to
    m["X-Mouth-Log"] = kind
    if rec.get("utt"):
        m["X-Mouth-Utt"] = rec["utt"]
    body = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in rec.items()
                     if v is not None and k not in ("directory",))
    m.set_content(body + "\n")
    for sub in ("tmp", "cur", "new"):
        (box / sub).mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns()}.P{os.getpid()}.{host}"
    tmp = box / "tmp" / name
    tmp.write_bytes(bytes(m))
    tmp.rename(box / "cur" / f"{name}:2,S")
    return mid


def entry(item: dict, kind: str, rec: dict) -> Optional[str]:
    """Log KIND for ITEM if its line asked for a mail log; never raises."""
    box = item.get("mail_log")
    if not box:
        return None
    try:
        return write(box, kind, rec, in_reply_to=item.get("log_root"))
    except Exception:  # noqa: BLE001 - a log that cannot be written must not stop the speech
        return None

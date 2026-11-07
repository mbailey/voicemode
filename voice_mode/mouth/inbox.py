"""Mail feeds mouth: a mail to ``mouth@<host>`` is a line.

Ruled by Mike, voice 21:40 Thu 2026-09-24 ("mail feeds mouth", slipbox
convention 515). Since 03:26 Sat 2026-09-26 the mouth's queue IS its
maildir (box.py): postfix delivers into ``new/``, ``mouth say`` drops into
the same ``new/``, and the player reads it. There is nothing left to
translate, so the watcher that turned mail into JSON queue files is gone.

``mouth mail`` (``watch``) is now the player, resident: the launch agent
``com.failmode.mouth-mail`` runs it, so a mail is spoken with no ``say`` to
start a player, and it never idles out. If another player holds the lock
it waits its turn. How a mail maps (body, Subject, ``Supersedes:``,
``X-Mouth-*``, ``Importance``, who may speak): box.py.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from .box import allowed, box_dir, speakable  # noqa: F401 - their old home
from .paths import mouth_dir


def mail_box() -> Path:
    env = os.environ.get("VOICEMODE_MOUTH_MAILBOX")
    return Path(env).expanduser() if env else Path.home() / ".mail" / "agents" / "mouth"


def watch(box: Optional[Path] = None, retry_s: float = 1.0, once: bool = False) -> int:
    """The player on the mailbox, resident. ``once``: speak what is there, then exit."""
    from . import maillog
    from .player import serve

    saved = {k: os.environ.get(k) for k in ("VOICEMODE_MOUTH_MAILBOX", maillog.LOG_VAR)}
    if box:
        os.environ["VOICEMODE_MOUTH_MAILBOX"] = str(box)
    bx = box_dir()
    # The box is its own log (Mike, 21:52-21:54 Thu), unless told otherwise.
    os.environ.setdefault(maillog.LOG_VAR, str(bx))
    try:
        return _watch(bx, retry_s, once)
    finally:  # a caller in the same process (a test) gets its environment back
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _watch(bx: Path, retry_s: float, once: bool) -> int:
    from . import maillog
    from .player import serve

    if once:
        return serve(idle_exit_s=0.5)
    log = maillog.box_from_env()
    started = time.strftime("%H:%M:%S")
    if log:
        maillog.write(log, "enabled", {"detail": f"playing {bx}", "pid": os.getpid()})
    print(json.dumps({"watching": str(bx), "mouth": str(mouth_dir()), "log": log}), flush=True)
    try:
        while True:
            serve(idle_exit_s=float("inf"))  # returns at once while another player holds the lock
            time.sleep(retry_s)
    finally:
        if log:
            maillog.write(log, "disabled", {"detail": f"stopped; up since {started}", "pid": os.getpid()})


if __name__ == "__main__":
    sys.exit(watch())

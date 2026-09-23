"""Where ``listen`` writes its lines: a SINK interface.

``Sink.write(line) -> seq``: the sink stamps ``ts`` and ``seq`` and appends
the line; the loop never numbers lines itself.

PROVISIONAL. The production writer is Pip's (VM-2270 task 1.1:
``heard_YYYY-MM-DD.jsonl`` beside ``conversation_logger.py``). This module
is NOT a second production writer: :class:`JsonlSink` writes to an explicit
path only, for tests and measurement, and slice do-004 swaps in an adapter
onto Pip's writer. The line shape follows
``openspec/changes/ambient-listen/specs/conversation-log/spec.md``.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Protocol


class Sink(Protocol):
    def write(self, line: dict) -> int:
        ...


def now_iso() -> str:
    """ISO 8601, local time, millisecond precision, with offset."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _last_seq(path: Path) -> int:
    """The highest ``seq`` already in the file (0 if none), reading from the end."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 65536))
            tail = f.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return 0
    for raw in reversed(tail.splitlines()):
        try:
            return int(json.loads(raw)["seq"])
        except (ValueError, KeyError, TypeError):
            continue
    return 0


class JsonlSink:
    """Append-only JSON lines at an explicit path; ``seq`` monotonic within the file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = _last_seq(self.path)

    def write(self, line: dict) -> int:
        with self._lock:
            self._seq += 1
            out = {"ts": now_iso(), "seq": self._seq, **line}
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(out, ensure_ascii=False) + "\n")
                f.flush()
            return self._seq


class MemorySink:
    """Lines kept in a list, with the same ``ts``/``seq`` stamping. A test double."""

    def __init__(self) -> None:
        self.lines: list[dict] = []

    def write(self, line: dict) -> int:
        out = {"ts": now_iso(), "seq": len(self.lines) + 1, **line}
        self.lines.append(out)
        return out["seq"]

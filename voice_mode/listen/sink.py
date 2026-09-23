"""Where capture writes its lines: through Pip's ``heard`` writer.

``Sink.write(line) -> seq`` is a thin seam, kept because the tests need
one. The production sink is :class:`HeardSink`, which writes through
``voice_mode.heard`` (VM-2270 task 1.1: ``heard_YYYY-MM-DD.jsonl`` under
``$VOICEMODE_BASE_DIR/logs/conversations/``). There is no second writer
here: ``heard`` stamps ``ts``, ``seq`` and ``v``, takes the lock, and owns
the file. :class:`MemorySink` is a test double.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol

from .. import heard


class Sink(Protocol):
    def write(self, line: dict) -> int:
        """Append one line (``kind`` plus fields); return its ``seq``."""
        ...


class HeardSink:
    """Every line through ``heard.append``; ``directory`` overrides the log dir (tests)."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = Path(directory).expanduser() if directory is not None else None

    def write(self, line: dict) -> int:
        fields = dict(line)
        kind = fields.pop("kind")
        return int(heard.append(kind, directory=self.directory, **fields)["seq"])


class MemorySink:
    """Lines kept in a list, stamped like ``heard`` does (``ts``, ``seq``). A test double."""

    def __init__(self) -> None:
        self.lines: list[dict] = []

    def write(self, line: dict) -> int:
        out = {"ts": heard._now_iso(), "seq": len(self.lines) + 1, **{k: v for k, v in line.items() if v is not None}}
        self.lines.append(out)
        return out["seq"]

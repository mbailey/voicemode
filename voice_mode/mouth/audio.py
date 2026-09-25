"""The mouth keeps what it says: one WAV per line, a JSON note beside it.

Cora's Samples section in the voice browser needs a line's audio after it
has been spoken (her recap, 04:13 Sat 2026-09-26; Mike's picker v2 wishes,
03:33, asked for cached samples). So every line whose synthesis FINISHED
(not cancelled, no error) is written, once it has played or been cut, to

    <audio dir>/<YYYY-MM-DD>/<utt>.wav     16-bit mono, the backend's rate
    <audio dir>/<YYYY-MM-DD>/<utt>.json    utt, voice, backend, speed, agent,
                                           session, text, requested_ts,
                                           sample_rate, dur_s, kept_ts

and its ``said`` record carries ``audio`` (the WAV path). A line played from
a file (``mouth play``) is not copied, and the ``silence`` backend (tests,
dry runs) is not kept.

- Where: ``$VOICEMODE_MOUTH_AUDIO_DIR``, else ``<mouth dir>/audio``.
- Off: ``VOICEMODE_MOUTH_KEEP_AUDIO=0`` (or ``off``/``no``/``false``).
- For how long: ``$VOICEMODE_MOUTH_AUDIO_DAYS`` days, default 7. Older day
  folders are removed after a keep, at most once an hour. ``0`` never prunes.

``mouth audio`` lists what is kept, newest first (``--voice``, ``--last``).
Keeping never stops the speech: any failure is swallowed and the line's
``said`` simply has no ``audio``.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import threading
import time
import wave
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from .paths import mouth_dir

DAYS = 7
PRUNE_EVERY_S = 3600.0
NOT_KEPT_BACKENDS = ("silence",)
_last_prune = {"t": 0.0}


def enabled() -> bool:
    v = os.environ.get("VOICEMODE_MOUTH_KEEP_AUDIO", "1").strip().lower()
    return v not in ("0", "off", "no", "false")


def audio_dir() -> Path:
    env = os.environ.get("VOICEMODE_MOUTH_AUDIO_DIR")
    return Path(env).expanduser() if env else mouth_dir() / "audio"


def days() -> float:
    try:
        return float(os.environ.get("VOICEMODE_MOUTH_AUDIO_DAYS", DAYS))
    except ValueError:
        return float(DAYS)


def wanted(item: dict, backend_name: str) -> bool:
    """Whether this line's audio is kept at all (before synthesis is known to finish)."""
    return enabled() and not item.get("file") and backend_name not in NOT_KEPT_BACKENDS


def pcm16(blocks: Iterable[np.ndarray]) -> bytes:
    """Float32 blocks in -1..1 as little-endian 16-bit PCM, clipped."""
    parts = [np.asarray(b, dtype=np.float32) for b in blocks if b is not None and len(b)]
    if not parts:
        return b""
    a = np.clip(np.concatenate(parts), -1.0, 1.0)
    return (a * 32767.0).round().astype("<i2").tobytes()


def keep(item: dict, blocks: Iterable[np.ndarray], sample_rate: int, backend_name: str,
         *, root: Optional[Path] = None, now: Optional[float] = None) -> Optional[Path]:
    """Write ITEM's audio and its note; return the WAV path, or None. Never raises."""
    try:
        if not wanted(item, backend_name):
            return None
        data = pcm16(blocks)
        if not data:
            return None
        now = time.time() if now is None else now
        root = audio_dir() if root is None else root
        day = root / _dt.date.fromtimestamp(now).isoformat()
        day.mkdir(parents=True, exist_ok=True)
        utt = str(item["utt"])
        wav, note = day / f"{utt}.wav", day / f"{utt}.json"
        tmp = day / f".{utt}.wav.tmp"
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(sample_rate))
            w.writeframes(data)
        os.replace(tmp, wav)
        meta = {"utt": utt, "voice": item.get("voice"), "backend": backend_name,
                "speed": item.get("speed"), "agent": item.get("agent"),
                "session": item.get("session"), "text": item.get("text"),
                "requested_ts": item.get("requested_ts"), "sample_rate": int(sample_rate),
                "dur_s": round(len(data) / 2 / sample_rate, 3),
                "kept_ts": _dt.datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds"),
                "wav": str(wav)}
        ntmp = day / f".{utt}.json.tmp"
        ntmp.write_text(json.dumps(meta, ensure_ascii=False) + "\n")
        os.replace(ntmp, note)
        # Off the player's thread: a day's rmtree must not put a gap between lines.
        threading.Thread(target=maybe_prune, args=(root,), kwargs={"now": now},
                         daemon=True, name="mouth-audio-prune").start()
        return wav
    except Exception:  # noqa: BLE001 - keeping audio must never stop the speech
        return None


def prune(root: Path, keep_days: float, now: Optional[float] = None) -> list[Path]:
    """Remove day folders older than KEEP_DAYS; return what was removed."""
    if keep_days <= 0 or not root.is_dir():
        return []
    now = time.time() if now is None else now
    cutoff = _dt.date.fromtimestamp(now - keep_days * 86400)
    gone = []
    for p in sorted(root.iterdir()):
        try:
            day = _dt.date.fromisoformat(p.name)
        except ValueError:
            continue  # not a day folder: never ours to remove
        if p.is_dir() and day < cutoff:
            shutil.rmtree(p, ignore_errors=True)
            gone.append(p)
    return gone


def maybe_prune(root: Path, now: Optional[float] = None) -> list[Path]:
    now = time.time() if now is None else now
    if now - _last_prune["t"] < PRUNE_EVERY_S:
        return []
    _last_prune["t"] = now
    return prune(root, days(), now=now)


def kept(root: Optional[Path] = None, voice: Optional[str] = None, last: Optional[int] = None) -> list[dict]:
    """The notes of kept lines, newest first; VOICE filters, LAST caps."""
    root = audio_dir() if root is None else root
    if not root.is_dir():
        return []
    out = []
    for day in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        notes = []
        for n in day.glob("*.json"):
            try:
                meta = json.loads(n.read_text())
            except (OSError, ValueError):
                continue
            if voice and meta.get("voice") != voice:
                continue
            if not Path(meta.get("wav") or n.with_suffix(".wav")).exists():
                continue
            notes.append(meta)
        notes.sort(key=lambda m: m.get("kept_ts") or "", reverse=True)
        out.extend(notes)
        if last and len(out) >= last:
            return out[:last]
    return out

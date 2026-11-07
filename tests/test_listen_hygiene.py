"""The listen spike's hard rules, checked in its source (VM-2274).

- It is FRESH: no import of converse's capture path (``voice_mode.tools.converse``,
  ``voice_mode.core``).
- It NEVER takes the conch: no import of ``voice_mode.conch*``.
- It makes NO SOUND: no playback module, no output stream, no ``sd.play``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import voice_mode.listen

PKG = Path(voice_mode.listen.__file__).parent
SOURCES = sorted(PKG.glob("*.py"))

FORBIDDEN_MODULE_PREFIXES = (
    "voice_mode.conch",  # conch, conch_ops, conch_queue, conch_notify
    "voice_mode.tools.converse",
    "voice_mode.core",
    "voice_mode.audio_player",
    "voice_mode.streaming",
    "simpleaudio",
    "pydub.playback",
)
FORBIDDEN_RELATIVE = ("conch", "conch_ops", "conch_queue", "conch_notify", "core", "audio_player", "streaming")
FORBIDDEN_NAMES = {"play", "playrec", "OutputStream", "Stream", "RawOutputStream", "RawStream"}


def imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [(node.level if hasattr(node, "level") else 0, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append((node.level, node.module or ""))
    return out


def test_the_package_has_sources():
    names = {p.name for p in SOURCES}
    assert {"loop.py", "sources.py", "detector.py", "chunker.py", "stt.py", "sink.py", "__main__.py"} <= names


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_conch_no_converse_no_playback_imports(path):
    tree = ast.parse(path.read_text())
    for level, mod in imported_modules(tree):
        if level == 0:
            assert not mod.startswith(FORBIDDEN_MODULE_PREFIXES), f"{path.name} imports {mod}"
        elif level == 2:  # from ..x import y -> voice_mode.x
            assert mod.split(".")[0] not in FORBIDDEN_RELATIVE and not mod.startswith("tools.converse"), f"{path.name} imports ..{mod}"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_output_audio_calls(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "sd":
            assert node.attr not in FORBIDDEN_NAMES, f"{path.name}:{node.lineno} uses sd.{node.attr}"


def test_importing_listen_does_not_load_the_conch_or_converse():
    import subprocess
    import sys

    code = (
        "import sys, voice_mode.listen, voice_mode.listen.__main__\n"
        "bad = [m for m in sys.modules if m.startswith(('voice_mode.conch', 'voice_mode.tools.converse', 'voice_mode.core'))]\n"
        "print(bad); sys.exit(1 if bad else 0)\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=PKG.parent.parent)
    assert proc.returncode == 0, proc.stdout + proc.stderr

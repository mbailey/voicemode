"""VM-2597: importing voice_mode must not need a working PortAudio.

GitHub CI went red with a pytest INTERNALERROR because ``import sounddevice``
fails on a headless runner, and five voice_mode modules imported it at module
level. They now bind ``sd = voice_mode._sounddevice.load()``: the real module
when it imports, a stand-in that fails at USE when it does not.

The headless half runs in a SUBPROCESS with a ``sounddevice.py`` shim first on
``PYTHONPATH`` that raises the way the real import does. A subprocess keeps it
clear of this session's armed audio guard and of ``sys.modules`` (never put a
fake sounddevice in ``sys.modules``: see CLAUDE.md, "The suite must never open
the real audio device"). The shim also means the child never reaches PortAudio.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from voice_mode import _sounddevice
from voice_mode._sounddevice import (
    SoundDeviceUnavailable,
    Unavailable,
    is_available,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every module that imported sounddevice eagerly before VM-2597, plus the
# server entry point (which imports the tools) and core (call-time import).
FORMERLY_EAGER = [
    "voice_mode.shared",
    "voice_mode.audio_player",
    "voice_mode.streaming",
    "voice_mode.tools.devices",
    "voice_mode.tools.converse",
]
ALSO_IMPORTED = ["voice_mode.server", "voice_mode.core"]

# The two ways ``import sounddevice`` fails on a host with no usable PortAudio.
SHIMS = {
    # The library is missing (sounddevice.py raises OSError when ctypes cannot
    # find libportaudio).
    "oserror": 'raise OSError("PortAudio library not found")\n',
    # The library loads but Pa_Initialize fails: sounddevice.PortAudioError,
    # an Exception subclass that is NOT an OSError.
    "portaudioerror": textwrap.dedent(
        """\
        class PortAudioError(Exception):
            pass
        raise PortAudioError(
            "Error initializing PortAudio: Internal PortAudio error [PaErrorCode -9986]"
        )
        """
    ),
}

CHILD = textwrap.dedent(
    """\
    import importlib, json, sys
    out = {"modules": {}}
    holders = []
    for name in sys.argv[1:]:
        mod = importlib.import_module(name)
        if hasattr(mod, "sd"):
            out["modules"][name] = type(mod.sd).__name__
            holders.append(mod)
    from voice_mode import streaming
    sd = streaming.sd
    out["shared_object"] = all(mod.sd is sd for mod in holders)
    out["reason"] = sd.reason
    try:
        sd.OutputStream(samplerate=24000, channels=1)
    except OSError as exc:
        out["call_error"] = [type(exc).__name__, str(exc), isinstance(exc, sd.PortAudioError)]
    out["callback_stop_is_exception"] = issubclass(sd.CallbackStop, Exception)
    print("RESULT " + json.dumps(out))
    """
)


def _run_headless(tmp_path: Path, shim: str) -> dict:
    shim_dir = tmp_path / f"shim-{shim}"
    shim_dir.mkdir()
    (shim_dir / "sounddevice.py").write_text(SHIMS[shim])
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(shim_dir), str(REPO_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    env.setdefault("OPENAI_API_KEY", "test-key")
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, *FORMERLY_EAGER, *ALSO_IMPORTED],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"importing voice_mode with sounddevice raising ({shim}) failed, "
        f"exit {proc.returncode}:\n{proc.stderr[-4000:]}"
    )
    line = next(l for l in proc.stdout.splitlines() if l.startswith("RESULT "))
    return json.loads(line[len("RESULT "):])


@pytest.mark.parametrize("shim", sorted(SHIMS))
def test_voice_mode_imports_without_portaudio(tmp_path, shim):
    result = _run_headless(tmp_path, shim)

    # Every formerly-eager module imported, and holds the stand-in.
    assert result["modules"] == {name: "Unavailable" for name in FORMERLY_EAGER}
    assert result["shared_object"], "modules should share one stand-in"
    expected = "OSError" if shim == "oserror" else "PortAudioError"
    assert result["reason"].startswith(expected + ":")

    # Use, not import, is where it fails, as an OSError naming the attribute
    # and the original cause; it is also the stand-in's PortAudioError.
    err_type, err_msg, is_pa_error = result["call_error"]
    assert err_type == "SoundDeviceUnavailable"
    assert "sd.OutputStream" in err_msg and expected in err_msg
    assert is_pa_error
    assert result["callback_stop_is_exception"]


# -- the stand-in itself (constructed directly; no sys.modules involved) ------


def _standin() -> Unavailable:
    return Unavailable(OSError("PortAudio library not found"))


def test_standin_attributes_raise_at_use():
    sd = _standin()
    with pytest.raises(SoundDeviceUnavailable, match=r"sd\.query_devices cannot run"):
        sd.query_devices()
    with pytest.raises(AttributeError, match=r"unavailable .*sd\.default\.device"):
        sd.default.device  # noqa: B018 - reading it is the use
    with pytest.raises(sd.PortAudioError):
        sd.InputStream(samplerate=16000)


def test_standin_exception_classes_are_real():
    sd = _standin()
    for name in ("PortAudioError", "CallbackStop", "CallbackAbort"):
        cls = getattr(sd, name)
        assert isinstance(cls, type) and issubclass(cls, Exception), name
    with pytest.raises(sd.CallbackStop):
        raise sd.CallbackStop()
    assert issubclass(SoundDeviceUnavailable, OSError)
    assert issubclass(SoundDeviceUnavailable, sd.PortAudioError)


def test_standin_is_patchable_like_the_module():
    """``patch.object(module.sd, "OutputStream")`` must work on a headless host."""
    from unittest.mock import MagicMock, patch

    sd = _standin()
    with patch.object(sd, "OutputStream") as fake:
        sd.OutputStream(samplerate=1).start()
    fake.assert_called_once_with(samplerate=1)
    assert isinstance(fake, MagicMock)
    # Restored to a raising attribute afterwards.
    with pytest.raises(SoundDeviceUnavailable):
        sd.OutputStream()


def test_standin_assignment_to_defaults_is_harmless():
    """``sd.default.samplerate = x`` stores a preference; it must not raise."""
    sd = _standin()
    sd.default.samplerate = 24000
    sd.default.channels = 1


def test_standin_is_falsy_and_says_why():
    sd = _standin()
    assert not sd
    assert "PortAudio library not found" in repr(sd)
    assert not is_available(sd)
    with pytest.raises(AttributeError):
        sd.__wrapped__  # noqa: B018 - dunders are never faked


# -- with a working sounddevice: nothing changes ------------------------------


@pytest.mark.skipif(not is_available(), reason="sounddevice unimportable (no PortAudio)")
def test_sd_is_the_real_module_when_it_imports():
    import sounddevice

    assert _sounddevice.load() is sounddevice
    from voice_mode import audio_player, shared, streaming
    from voice_mode.tools import converse, devices

    for mod in (shared, audio_player, streaming, devices, converse):
        assert mod.sd is sounddevice, mod.__name__

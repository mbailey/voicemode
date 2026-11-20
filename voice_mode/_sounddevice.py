"""``sounddevice``, or a stand-in when PortAudio cannot be reached (VM-2597).

``import sounddevice`` does real work at import time: it loads the PortAudio
library (``OSError`` when it is missing) and calls ``Pa_Initialize``
(``sounddevice.PortAudioError``, which is NOT an ``OSError``, when no host API
can start: a headless server, a container, a CI runner with no sound server).
A module-level ``import sounddevice as sd`` therefore made ``import voice_mode``
itself fail on such a host, before any audio was ever wanted.

Modules bind ``sd = load()`` at module level instead:

- With a working PortAudio, ``sd`` **is** the ``sounddevice`` module
  (``sd is sounddevice``). Runtime behaviour, ``patch("<module>.sd...")`` seams
  and the test audio guard's identity checks are unchanged.
- Without one, ``sd`` is an :class:`Unavailable` stand-in. Importing succeeds;
  the failure surfaces at USE, as :class:`SoundDeviceUnavailable` naming the
  attribute and the original import error. Any attribute can be read (so
  ``patch.object(module.sd, "OutputStream", ...)`` works on a headless host),
  and the exception classes the code raises (``PortAudioError``,
  ``CallbackStop``, ``CallbackAbort``) are real exception classes.

The import is attempted once per process and the result cached, so every
module sees the same object.
"""

from __future__ import annotations

from typing import Any, Optional


class PortAudioError(Exception):
    """Stand-in for ``sounddevice.PortAudioError`` when sounddevice is absent."""


class CallbackStop(Exception):
    """Stand-in for ``sounddevice.CallbackStop`` when sounddevice is absent."""


class CallbackAbort(Exception):
    """Stand-in for ``sounddevice.CallbackAbort`` when sounddevice is absent."""


class SoundDeviceUnavailable(PortAudioError, OSError):
    """Raised when audio is used on a host where sounddevice could not import.

    It is both the stand-in's ``PortAudioError`` and an ``OSError``, so an
    ``except sd.PortAudioError`` or an ``except OSError`` around audio code
    handles it as it would a real device failure.
    """


class _Missing:
    """One attribute of an unavailable sounddevice.

    Calling it raises :class:`SoundDeviceUnavailable`; reading a sub-attribute
    (``sd.default.device``) raises ``AttributeError`` naming the cause.
    Assigning to it is allowed (``sd.default.samplerate = 24000`` only stores a
    preference and opens nothing); the failure comes at the first real use.
    """

    def __init__(self, name: str, reason: str) -> None:
        self._name = name
        self._reason = reason

    def _fail(self, what: str) -> SoundDeviceUnavailable:
        return SoundDeviceUnavailable(
            f"sounddevice is unavailable ({self._reason}); sd.{what} cannot run"
        )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise self._fail(self._name)

    def __getattr__(self, attr: str) -> Any:
        # An AttributeError, not SoundDeviceUnavailable: introspection
        # (``getattr(x, name, None)`` in inspect, mock, asyncio) only tolerates
        # AttributeError.  The message still names the cause.
        raise AttributeError(
            f"sounddevice is unavailable ({self._reason}); "
            f"sd.{self._name}.{attr} does not exist"
        )

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"<sounddevice unavailable: sd.{self._name}>"


class Unavailable:
    """Stands in for the ``sounddevice`` module when it could not be imported."""

    PortAudioError = PortAudioError
    CallbackStop = CallbackStop
    CallbackAbort = CallbackAbort

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.reason = f"{type(error).__name__}: {error}"

    def __getattr__(self, name: str) -> Any:
        # Dunder lookups (copy, pickle, mock introspection) must see a plain
        # AttributeError, not a fake attribute.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _Missing(name, self.reason)

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"<sounddevice unavailable ({self.reason})>"


_cached: Optional[Any] = None


def load() -> Any:
    """Return the ``sounddevice`` module, or an :class:`Unavailable` stand-in.

    Catches ``Exception`` broadly: a missing library is an ``OSError``, but a
    failed ``Pa_Initialize`` is ``sounddevice.PortAudioError``, which is not.
    """
    global _cached
    if _cached is None:
        try:
            import sounddevice
        except Exception as exc:  # OSError (no library) or PortAudioError (no host API)
            _cached = Unavailable(exc)
        else:
            _cached = sounddevice
    return _cached


def is_available(sd: Any = None) -> bool:
    """True when ``sd`` (default: :func:`load`'s result) is not the stand-in."""
    return not isinstance(load() if sd is None else sd, Unavailable)

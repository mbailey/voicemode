"""VM-2072 — the sounddevice (PortAudio) half of the audio guard.

WHERE THE GUARD GOES, AND WHY IT IS NOT A LIST
----------------------------------------------
Three concentric layers, because each one covers what the one outside it
cannot:

1. **Derived entry points.**  At arm time ``_sd_entrypoints.analyse()`` reads
   the *installed* sounddevice and works out mechanically which public
   callables can reach a ``_lib.Pa_*`` call.  The covered set is therefore
   derived, never typed.  This matters concretely: the foreman's hand-written
   list of this repo's sounddevice call sites decayed **within one day** (10
   listed, 12 real — and one of the two missing sites was caught RED by the
   instrument).  Derivation does not decay.

2. **The ``_StreamBase.__init__`` choke point.**  Every stream class in
   sounddevice, public or not, constructs through it — including a subclass
   written by somebody who never heard of this guard.  VM-2072's fourth
   reviewer proved this by defining a ``_StreamBase`` subclass inside a review
   script that no enumeration had ever seen; the guard caught it.

3. **The ``_lib`` backstop.**  ``_lib`` is sounddevice's CFFI handle on
   PortAudio: it *is* the hardware boundary.  Anything that reaches a device
   without crossing layers 1 or 2 still has to call ``_lib.Pa_*``.  This layer
   is what the guard "fails safe on" — the answer to the question the earlier
   instrument could not answer about itself, after its advertised fail-safe
   turned out to cover unknown *symbols* but not unwalked *edges*.

ARMING HAS TWO HALVES
---------------------
Patching the module attribute covers call-time lookups (``sd.play(...)``),
lazy in-function imports, and importers that have not run yet.  It does NOT
cover a ``from sounddevice import play`` alias, which binds the *function
object*: a module-layer patch never reaches it.  That is a property of Python,
not of this repo — CPython's own ``subprocess`` holds
``from _posixsubprocess import fork_exec as _fork_exec`` and VM-2072's rca-001
watched a caller execute straight past a choke-point guard because of it.  So
arming also sweeps ``sys.modules`` and rebinds existing aliases **by object
identity**, which discovers the alias set instead of listing it.

A GUARD THAT CAN BE SILENTLY DISARMED IS A DEAD GUARD
-----------------------------------------------------
``importlib.reload(sounddevice)`` removes every patch.  ``mock.patch(
'sounddevice.wait')`` lifts one for a test's duration — live today at
``tests/test_concurrent_stdio.py:87``.  Neither announces itself.  So the
sounddevice module object is given a ``__setattr__`` that RECORDS any rebinding
of a guarded name: the window becomes visible instead of silent, and the
plugin's per-test check re-arms anything that went missing.  The offending test
is deliberately not "fixed" — hiding the window would remove the evidence.
"""

from __future__ import annotations

import datetime as _dt
import inspect
import sys
import types

from . import (
    MODE_BLOCK,
    MODE_MUTE,
    AudioDeviceTouchedInTest,
    note,
    record_hit,
)
from . import _sd_entrypoints as _enum

#: PortAudio symbols the backstop deliberately lets through, each with the
#: reason.  Deliberate non-coverage is REPORTED, never silent: this dict is
#: printed in the terminal summary and carried in every JSON report.
BACKSTOP_PASSTHROUGH: dict = {
    "Pa_GetErrorText": "renders an error code as text; no device involved — and "
                       "blocking it would corrupt PortAudioError.__str__, the "
                       "known false-positive site",
    "Pa_GetVersion": "library version number",
    "Pa_GetVersionText": "library version string",
    "Pa_GetVersionInfo": "library version struct",
    "Pa_GetSampleSize": "arithmetic on a sample format constant",
    "Pa_HostApiTypeIdToHostApiIndex": "index arithmetic over already-loaded host APIs",
    "Pa_HostApiDeviceIndexToDeviceIndex": "index arithmetic over already-loaded host APIs",
    "Pa_GetLastHostErrorInfo": "reads the last error struct",
    "Pa_Sleep": "sleeps",
    "PaMacCore_SetupStreamInfo": "fills a settings struct; opens nothing",
    "PaMacCore_SetupChannelMap": "fills a settings struct; opens nothing",
    "Pa_Initialize": "already ran at import of sounddevice, long before the guard "
                     "could arm; blocking it here would only break teardown",
    "Pa_Terminate": "interpreter-shutdown counterpart of Pa_Initialize; blocking "
                    "it produces noise at exit and protects nothing",
}

_ORIGINALS: list = []          # (owner, name, original, was_in_dict)
_PATCHED_PAIRS: list = []      # (original, replacement) for the alias sweep
_INSTALLED: list = []          # (owner, name, replacement) for the armed check
_GUARDED_MODULE_NAMES: set = set()
_LIFTED: dict = {}             # attribute -> event, currently-lifted guards
#: The class objects we patched, so a RELOAD is detectable: reload rebuilds
#: every class, leaving our references pointing at objects nothing uses.
_ARMED_CLASSES: dict = {}
#: The module OBJECT we armed, so a WHOLESALE REPLACEMENT is detectable.
#: ``sys.modules['sounddevice'] = MagicMock()`` is a different condition from a
#: reload and needs a different answer -- see ``module_replaced()``.
_ARMED_MODULE: dict = {"object": None}
_STATE: dict = {}


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------


def _inert_result(classification: str):
    """What a muted call hands back.

    ``mute`` mode exists so an opt-in ``-m audio`` run can exercise audio code
    paths without a device.  The stand-in never calls PortAudio, so the opt-in
    path is device-safe *by construction* rather than by a sink someone has to
    configure correctly.
    """
    if classification == "probes_device":
        return []
    return None


def _blocker(entry_point: str, classification: str, mode: str):
    def guarded(*args, **kwargs):
        if mode == MODE_MUTE:
            record_hit(
                "sounddevice", entry_point, "muted",
                classification=classification,
                detail="opt-in run: inert stand-in returned, PortAudio not called",
            )
            return _inert_result(classification)
        record_hit(
            "sounddevice", entry_point, "blocked",
            classification=classification,
        )
        raise AudioDeviceTouchedInTest(
            f"VM-2072: test code called sounddevice.{entry_point}() "
            f"({classification}). The real audio device was NOT opened — the "
            "audio guard blocked it. If this test genuinely needs a device, "
            "mark it @pytest.mark.audio (it will run muted under -m audio); if "
            "it does not, mock the audio call it is not asserting about."
        )

    guarded.__name__ = f"vm2072_audio_guard_{entry_point.replace('.', '_')}"
    guarded.__qualname__ = guarded.__name__
    guarded.__doc__ = f"VM-2072 audio guard standing in for sounddevice.{entry_point}"
    guarded.__vm2072_audio_guard__ = entry_point
    return guarded


class _PortAudioBackstop:
    """Guards the PortAudio C library handle itself — the hardware boundary.

    Layers 1 and 2 name the crossing precisely; this one cannot be evaded by a
    surface nobody derived.  It fires only for calls that got past them, so in
    a healthy run it is silent — which is exactly the property that makes it a
    fail-safe rather than a duplicate.
    """

    def __init__(self, real, mode: str):
        self.__dict__["_vm2072_real"] = real
        self.__dict__["_vm2072_mode"] = mode
        self.__dict__["_vm2072_cache"] = {}

    def __getattr__(self, name):
        real_attr = getattr(self.__dict__["_vm2072_real"], name)
        # PortAudio's own naming: functions are Pa_Something / PaMacCore_Something;
        # constants are paSomething.  Constants are values, not calls.
        if not name.startswith(("Pa_", "PaMacCore_")):
            return real_attr
        if name in BACKSTOP_PASSTHROUGH:
            return real_attr
        cache = self.__dict__["_vm2072_cache"]
        if name not in cache:
            cache[name] = _backstop_guard(name, self.__dict__["_vm2072_mode"])
        return cache[name]

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"<VM-2072 PortAudio backstop around {self.__dict__['_vm2072_real']!r}>"


def _backstop_guard(symbol: str, mode: str):
    def guarded(*args, **kwargs):
        if mode == MODE_MUTE:
            record_hit(
                "sounddevice", f"_lib.{symbol}", "muted",
                classification="portaudio_backstop",
                detail="opt-in run: PortAudio call suppressed at the C boundary",
            )
            return 0
        record_hit(
            "sounddevice", f"_lib.{symbol}", "blocked",
            classification="portaudio_backstop",
        )
        raise AudioDeviceTouchedInTest(
            f"VM-2072: test code reached PortAudio directly via _lib.{symbol}() — "
            "past every derived entry point. The device was NOT opened; the "
            "backstop caught it. This means the derived entry-point set has a "
            "hole worth reporting on VM-2072."
        )

    guarded.__name__ = f"vm2072_portaudio_backstop_{symbol}"
    guarded.__vm2072_audio_guard__ = f"_lib.{symbol}"
    return guarded


# ---------------------------------------------------------------------------
# patching
# ---------------------------------------------------------------------------


def _patch_attr(owner, name: str, replacement, track_pair: bool = True) -> None:
    was_in_dict = name in getattr(owner, "__dict__", {})
    original = (
        inspect.getattr_static(owner, name, None)
        if isinstance(owner, type)
        else getattr(owner, name, None)
    )
    _ORIGINALS.append((owner, name, original, was_in_dict))
    _INSTALLED.append((owner, name, replacement))
    if track_pair and original is not None:
        _PATCHED_PAIRS.append((original, replacement))
    _set(owner, name, replacement)


def _set(owner, name: str, value) -> None:
    """Set an attribute without tripping our own module watcher."""
    if isinstance(owner, types.ModuleType):
        types.ModuleType.__setattr__(owner, name, value)
    else:
        setattr(owner, name, value)


def _patch_member(owner, name: str, entry_point: str, classification: str, mode: str) -> str:
    """Guard one attribute of a class, PRESERVING WHAT KIND OF ATTRIBUTE IT IS.

    ``getattr_static`` is load-bearing, not tidiness.  Replacing a ``property``
    with a bare function turns ``stream.active`` from a call into an attribute
    read: the guard would never fire, silently, and the semantics would change
    under the code being tested.  Same silent-failure family as the defect this
    whole task exists to close, so a property is re-wrapped AS a property.
    """
    static = inspect.getattr_static(owner, name, None)
    guard = _blocker(entry_point, classification, mode)
    if isinstance(static, property):
        _patch_attr(owner, name, property(guard))
        return "property"
    if isinstance(static, staticmethod):
        _patch_attr(owner, name, staticmethod(guard))
        return "staticmethod"
    if isinstance(static, classmethod):
        _patch_attr(owner, name, classmethod(guard))
        return "classmethod"
    _patch_attr(owner, name, guard)
    return "method"


def _rebind_aliases() -> list:
    """Rebind every existing ``from sounddevice import X`` alias, by identity.

    Half two of arming.  The module-layer patch covers call-time lookups; an
    alias bound before we armed holds the original function object and would
    walk straight past it.  One sweep of ``sys.modules`` comparing by ``id()``,
    so the alias set is discovered rather than listed.
    """
    if not _PATCHED_PAIRS:
        return []
    by_id = {id(original): replacement for original, replacement in _PATCHED_PAIRS}
    rebound: list = []
    for modname, module in list(sys.modules.items()):
        if module is None or modname.startswith("tests.audio_guard"):
            continue
        namespace = getattr(module, "__dict__", None)
        if not isinstance(namespace, dict):
            continue
        for attr, value in list(namespace.items()):
            replacement = by_id.get(id(value))
            if replacement is None or value is replacement:
                continue
            try:
                _set(module, attr, replacement)
            except Exception:  # pragma: no cover - defensive
                continue
            _ORIGINALS.append((module, attr, value, True))
            rebound.append(f"{modname}.{attr}")
    return rebound


class _WatchedModule(types.ModuleType):
    """The sounddevice module, with rebinding of a guarded name made visible.

    This is how a lifted guard stops being silent.  ``mock.patch`` and
    ``importlib.reload`` both go through ``setattr`` on the module; neither
    announces itself, and both leave a window in which the real device is
    reachable.  We do NOT prevent the rebinding — a test that patches
    ``sounddevice.wait`` has a right to — we RECORD it, so the window appears
    in the run's events instead of nowhere.
    """

    def __setattr__(self, name, value):
        if name in _GUARDED_MODULE_NAMES:
            guarded = getattr(value, "__vm2072_audio_guard__", None)
            if guarded is None:
                _LIFTED[name] = note(
                    "guard-lifted",
                    attribute=f"sounddevice.{name}",
                    replaced_with=type(value).__name__,
                    detail="a guarded sounddevice attribute was rebound; the "
                           "device is unguarded at this entry point until it is "
                           "restored or re-armed",
                )
            elif name in _LIFTED:
                _LIFTED.pop(name, None)
                note("guard-restored", attribute=f"sounddevice.{name}")
        types.ModuleType.__setattr__(self, name, value)


def _is_sounddevice_module(obj) -> bool:
    """Is this object something we can actually derive guards from?

    The discriminator is ``isinstance(obj, ModuleType)`` plus the three
    attributes the derivation needs.  A ``MagicMock`` satisfies ``hasattr`` for
    every name in the universe, so ``hasattr`` alone answers "yes" to a stand-in
    that has no source, no ``_lib`` and no PortAudio behind it — which is
    exactly how ``_enum.analyse()`` came to be handed one.
    """
    if not isinstance(obj, types.ModuleType):
        return False
    if getattr(obj, "__file__", None) is None:
        return False
    return all(hasattr(obj, name)
               for name in ("_lib", "_StreamBase", "query_devices"))


def module_replaced() -> dict | None:
    """Has ``sys.modules['sounddevice']`` been swapped for a different object?

    A DIFFERENT CONDITION FROM A RELOAD, WITH A DIFFERENT ANSWER.  A reload
    re-executes the module body into the SAME module object, so re-deriving and
    re-arming is exactly right.  A wholesale replacement --
    ``sys.modules['sounddevice'] = MagicMock()``, which one test file in this
    repo did at module level, i.e. during COLLECTION, i.e. for the rest of the
    session -- leaves an object that is not sounddevice at all.  Re-deriving
    against it is meaningless, and attempting it raises out of the teardown
    hookwrapper: measured on 2026-08-19, one line put an ERROR on all 2116 tests
    of a full run.  A guard that does that to a suite gets deleted within a
    week, which is the decay this task exists to prevent, arriving through the
    guard instead of through the marker.

    So the two are told apart here and answered separately.  Returns ``None``
    when the armed module is still in place, otherwise a description of what is
    there now -- including whether it is a real sounddevice we could adopt.
    """
    armed = _ARMED_MODULE.get("object")
    if armed is None:
        return None
    current = sys.modules.get("sounddevice")
    if current is armed:
        return None
    return {
        "replaced_with": "<removed from sys.modules>" if current is None
                         else type(current).__name__,
        "is_module": isinstance(current, types.ModuleType),
        "adoptable": _is_sounddevice_module(current),
        "armed_module_file": getattr(armed, "__file__", None),
    }


def adopt_replacement() -> bool:
    """Arm a REAL sounddevice that has taken the armed module's place.

    Only ever called for the ``adoptable`` case: someone put a genuine
    sounddevice module object into ``sys.modules`` (a re-import, a restore).
    That IS coverable, so it is covered rather than reported as a hole.
    """
    if not _is_sounddevice_module(sys.modules.get("sounddevice")):
        return False
    mode = _STATE.get("mode", MODE_BLOCK)
    _forget_state()
    arm(mode)
    return True


def _unarmed_state(mode: str, reason: str) -> dict:
    """The coverage description for "we could not arm", with every key present.

    Returning a shaped dict rather than raising is deliberate: every consumer of
    this state is a REPORTING path, and a reporting path that explodes takes the
    run's only record of what happened with it.
    """
    _STATE.update({
        "sounddevice_version": None,
        "sounddevice_file": None,
        "derived_entry_points": 0,
        "device_touching": 0,
        "covered": {},
        "guard_count": 0,
        "mediated": {},
        "rebound_aliases": [],
        "backstop_installed": False,
        "backstop_passthrough": BACKSTOP_PASSTHROUGH,
        "rebinding_watcher": False,
        "mode": mode,
        "armed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "not_armed_reason": reason,
    })
    note("sounddevice-layer-not-armed", layer="sounddevice", detail=reason)
    return dict(_STATE)


def arm(mode: str = MODE_BLOCK) -> dict:
    """Install every layer.  Returns the coverage description for the report."""
    sd = sys.modules.get("sounddevice")
    if sd is None:
        import sounddevice as sd  # noqa: F811 - first import, normal path
    if not _is_sounddevice_module(sd):
        # Never derive against a stand-in.  This is the arm-time half of
        # module_replaced(): if something already occupies sounddevice's name
        # before we get here, say so and stay unarmed rather than crash.
        return _unarmed_state(
            mode,
            "sys.modules['sounddevice'] is a "
            f"{type(sd).__name__}, not the sounddevice module: guards cannot be "
            "derived from it and none were installed",
        )
    _ARMED_MODULE["object"] = sd

    report = _enum.analyse(sd)
    covered: dict = {}
    mediated: dict = {}

    for name in report["device_touching"]:
        entry = report["entry_points"][name]
        obj = getattr(sd, name)
        if isinstance(obj, type):
            targets = entry.get("guard_targets") or {}
            armed = {}
            for member, member_class in targets.items():
                if inspect.getattr_static(obj, member, None) is None:
                    continue  # derived from source, absent at runtime
                kind = _patch_member(obj, member, f"{name}.{member}", member_class, mode)
                armed[member] = {"classification": member_class, "kind": kind}
            if armed:
                covered[name] = armed
                _ARMED_CLASSES[name] = obj
            else:
                # Device-touching, but every route to PortAudio runs through a
                # public entry point guarded above.  RECORDED, not silently
                # skipped: a gap nobody wrote down is how this task's defects
                # survived in the first place.
                mediated[name] = {
                    "classification": entry["classification"],
                    "mediated_by": entry.get("mediated_by", []),
                }
        else:
            _patch_attr(sd, name, _blocker(name, entry["classification"], mode))
            _GUARDED_MODULE_NAMES.add(name)
            covered[name] = {
                name: {"classification": entry["classification"], "kind": "function"}
            }

    # Layer 2 — the private choke point every stream class constructs through,
    # including subclasses no enumeration has ever seen.
    base = getattr(sd, "_StreamBase", None)
    if base is not None:
        _patch_attr(base, "__init__",
                    _blocker("_StreamBase.__init__", "opens_device", mode))
        covered["_StreamBase"] = {
            "__init__": {"classification": "opens_device", "kind": "method"}
        }

    # Layer 3 — the PortAudio boundary itself.
    backstop = None
    real_lib = getattr(sd, "_lib", None)
    if isinstance(real_lib, _PortAudioBackstop):
        # Arming again over a live backstop (a reload repair, or adopting a
        # replacement) must not wrap a wrapper: unwrap to the real CFFI handle,
        # so re-arming N times leaves exactly one layer between the caller and
        # PortAudio.
        real_lib = real_lib.__dict__["_vm2072_real"]
    if real_lib is not None:
        backstop = _PortAudioBackstop(real_lib, mode)
        _patch_attr(sd, "_lib", backstop)
        _GUARDED_MODULE_NAMES.add("_lib")

    aliases = _rebind_aliases()

    # Make a lifted guard visible (see _WatchedModule).
    watched = False
    try:
        sd.__class__ = _WatchedModule
        watched = True
    except Exception as exc:  # pragma: no cover - defensive
        note("guard-watcher-unavailable", detail=repr(exc))

    _STATE.update({
        "sounddevice_version": report["sounddevice_version"],
        "sounddevice_file": report["sounddevice_file"],
        "derived_entry_points": len(report["entry_points"]),
        "device_touching": len(report["device_touching"]),
        "covered": covered,
        "guard_count": sum(len(v) for v in covered.values()),
        "mediated": mediated,
        "rebound_aliases": aliases,
        "backstop_installed": backstop is not None,
        "backstop_passthrough": BACKSTOP_PASSTHROUGH,
        "rebinding_watcher": watched,
        "mode": mode,
        "armed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    })
    return dict(_STATE)


def verify_armed() -> list:
    """Which guards are no longer installed.

    Called at every test teardown by the plugin.  A guard that quietly went
    missing is the dead-guard case; this is what makes the window observable.
    """
    missing = []
    for owner, name, replacement in _INSTALLED:
        try:
            current = (
                inspect.getattr_static(owner, name, None)
                if isinstance(owner, type)
                else getattr(owner, name, None)
            )
        except Exception:  # pragma: no cover - defensive
            continue
        if current is replacement:
            continue
        if isinstance(replacement, property) and isinstance(current, property):
            if current.fget is replacement.fget:
                continue
        owner_name = getattr(owner, "__name__", repr(owner))
        missing.append({"owner": owner_name, "attribute": name,
                        "found": type(current).__name__})
    return missing


def reloaded() -> bool:
    """Has the sounddevice module been rebuilt under us?

    ``importlib.reload(sounddevice)`` re-executes the module body into the same
    module object, which (a) writes straight into ``__dict__``, so the rebinding
    watcher never sees it, and (b) builds BRAND NEW class objects — so every
    class guard we installed is now on an object nothing refers to any more.
    Re-installing attribute by attribute would restore the module-level
    functions and silently leave the streams unguarded, which is a worse state
    than either: a guard that *looks* re-armed.  So a reload is detected as a
    reload and answered with a complete re-arm.

    A WHOLESALE REPLACEMENT IS NOT A RELOAD and must not be answered as one:
    this used to read ``import sounddevice as sd``, so a ``MagicMock`` sitting
    in ``sys.modules`` answered every ``getattr`` with a fresh Mock, reported
    itself as a reload, and sent ``rearm()`` into ``_enum.analyse(MagicMock)``.
    The question is asked of the module we ARMED; replacement is
    ``module_replaced()``'s question, and it has its own answer.
    """
    sd = _ARMED_MODULE.get("object")
    if sd is None or module_replaced() is not None:
        return False

    for name, cls in _ARMED_CLASSES.items():
        if getattr(sd, name, None) is not cls:
            return True
    if _STATE.get("backstop_installed") and not isinstance(
        getattr(sd, "_lib", None), _PortAudioBackstop
    ):
        return True
    return False


def _forget_state() -> None:
    _ARMED_MODULE["object"] = None
    _ORIGINALS.clear()
    _INSTALLED.clear()
    _PATCHED_PAIRS.clear()
    _GUARDED_MODULE_NAMES.clear()
    _ARMED_CLASSES.clear()
    _LIFTED.clear()


def rearm(missing: list) -> int:
    """Re-install guards that went missing, so a window is at most one test long."""
    if reloaded():
        mode = _STATE.get("mode", MODE_BLOCK)
        note(
            "guard-full-rearm",
            layer="sounddevice",
            detail="sounddevice was reloaded: every guard was silently removed "
                   "and its classes rebuilt, so the guard was derived and armed "
                   "again from scratch",
        )
        _forget_state()
        arm(mode)
        return -1

    restored = 0
    for owner, name, replacement in _INSTALLED:
        owner_name = getattr(owner, "__name__", repr(owner))
        if not any(m["owner"] == owner_name and m["attribute"] == name for m in missing):
            continue
        try:
            _set(owner, name, replacement)
            restored += 1
        except Exception:  # pragma: no cover - defensive
            continue
    return restored


def disarm() -> None:
    _ARMED_MODULE["object"] = None
    _INSTALLED.clear()
    while _ORIGINALS:
        owner, name, original, was_in_dict = _ORIGINALS.pop()
        if was_in_dict or not isinstance(owner, type):
            _set(owner, name, original)
        else:
            try:
                delattr(owner, name)
            except AttributeError:  # pragma: no cover - defensive
                _set(owner, name, original)
    _PATCHED_PAIRS.clear()
    _GUARDED_MODULE_NAMES.clear()
    _LIFTED.clear()

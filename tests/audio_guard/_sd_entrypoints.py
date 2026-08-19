#!/usr/bin/env python3
"""VM-2072 — derive the device-touching sounddevice entry points.

VENDORED, NOT WRITTEN HERE.  Lifted verbatim from VM-2072 repro-001's
``enumerate_sounddevice_entrypoints.py`` (task evidence,
``evidence/repro-001/``), where it was built as the reproduction instrument and
then re-verified by three further reviewers.  fix-001 adopts it unchanged so
the guard's covered set is DERIVED AT ARM TIME from the *installed*
sounddevice rather than typed out — the property VM-2072's acceptance requires
and that a hand-written list demonstrably does not have (the foreman's own
10-site list of sounddevice importers decayed within a day; the derivation
found 12).

WHY THIS EXISTS
---------------
The acceptance for repro-001 says the enumeration of device-opening entry
points must be "derived from the sounddevice API, not a guessed subset, and
recorded".  A hand-written list (``play``, ``rec``, ``OutputStream``, ...) is a
guess: it is a snapshot of what one agent remembered on one afternoon, and it
silently goes stale when sounddevice adds a surface or voicemode starts using
one nobody listed.

So instead of listing names, this script reads the *installed* sounddevice
module and works out, mechanically, which public callables can reach PortAudio.

METHOD
------
1. Parse the source of the installed ``sounddevice`` module with ``ast``.
2. Build a call graph over every module-level function, every class method and
   every nested/closure function defined in that source.
3. For each node, record the ``_lib.Pa_*`` symbols it references directly.
   ``_lib`` is sounddevice's CFFI handle on the PortAudio C library, so a
   ``_lib.Pa_XXX`` reference IS the hardware boundary; nothing reaches a device
   without crossing it.
4. Propagate those references transitively across the call graph (fixed point),
   so ``play`` inherits everything ``OutputStream.__init__`` reaches, and so on.
5. Classify each PUBLIC entry point by the most severe PortAudio symbol it can
   reach, using the severity table below.
6. For each public CLASS, work out WHICH OF ITS METHODS carries that
   reachability, so the instrument can guard the method the derivation actually
   implicates instead of guessing ``__init__``.  See WHERE THE GUARD GOES.

WHERE THE GUARD GOES
--------------------
Classifying a class is not the same as knowing where to intercept it.  A class
is device-touching if *any* of its methods reaches PortAudio, but the guard has
to go on that method.  ``PortAudioError`` is device-touching because of
``__str__``; its ``__init__`` does not appear in the call graph at all.  So
``guard_targets`` names the methods, derived the same way the classification is.

Second-order refinement, ``mediated``: if a method's ONLY route to PortAudio is
through another PUBLIC entry point that this instrument already guards, it needs
no guard of its own — the crossing is caught at that entry point, with a more
accurate name.  Guarding the outer method as well buys nothing and costs false
positives, because AST reachability is path-INSENSITIVE: it cannot see that
``PortAudioError.__str__`` only calls ``query_hostapis`` on the 3-argument
branch.  ``unmediated`` reachability is therefore computed by re-running the
fixed point with propagation blocked at public entry points, and the guard
targets come from that.  Entry points left unguarded for this reason are
reported under ``mediated_by`` -- deliberately, visibly, and never silently.

FAIL-SAFE
---------
``_lib`` also carries PortAudio's *constants* (``paClipOff``, ``paMME``,
``paInputOverflow``, ...).  Those are enum values, not calls, and PortAudio's
own naming distinguishes them: functions are ``Pa_Something`` / host-API
functions are ``PaMacCore_Something``; constants are ``paSomething`` (lowercase
``pa`` prefix, no underscore).  Constants are classified ``inert`` by rule, not
by table.

Any *function* symbol that is not in ``PA_SEVERITY`` is reported as
``unclassified`` and treated as ``opens_device`` (the most severe class).  A new
PortAudio function therefore makes the guard stricter, never quieter.  The
unclassified list is printed in the report so a human can triage it.

USAGE
-----
    python enumerate_sounddevice_entrypoints.py            # human summary
    python enumerate_sounddevice_entrypoints.py --json OUT # machine record

Run it with the interpreter whose sounddevice you care about (voicemode's
.venv), because it reports on the *installed* version, not a vendored copy.
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import inspect
import json
import sys
from typing import Dict, Iterable, List, Set

# ---------------------------------------------------------------------------
# Severity table: what each PortAudio C symbol means for a live human's device.
#
# The table is keyed on the PortAudio API (a C API that changes about once a
# decade), NOT on sounddevice's Python surface (which is what actually drifts).
# Anything absent is treated as opens_device -- see FAIL-SAFE above.
# ---------------------------------------------------------------------------
PA_SEVERITY: Dict[str, str] = {
    # --- opens_device: acquires or drives a real stream on real hardware -----
    "Pa_OpenStream": "opens_device",
    "Pa_OpenDefaultStream": "opens_device",
    "Pa_StartStream": "opens_device",
    "Pa_StopStream": "opens_device",
    "Pa_AbortStream": "opens_device",
    "Pa_CloseStream": "opens_device",
    "Pa_WriteStream": "opens_device",
    "Pa_ReadStream": "opens_device",
    "Pa_IsStreamActive": "opens_device",
    "Pa_IsStreamStopped": "opens_device",
    "Pa_GetStreamTime": "opens_device",
    "Pa_GetStreamCpuLoad": "opens_device",
    "Pa_GetStreamInfo": "opens_device",
    "Pa_GetStreamWriteAvailable": "opens_device",
    "Pa_GetStreamReadAvailable": "opens_device",
    "Pa_SetStreamFinishedCallback": "opens_device",
    # --- probes_device: talks to PortAudio/the host API, opens no stream -----
    "Pa_Initialize": "probes_device",
    "Pa_Terminate": "probes_device",
    "Pa_IsFormatSupported": "probes_device",
    "Pa_GetDeviceCount": "probes_device",
    "Pa_GetDeviceInfo": "probes_device",
    "Pa_GetDefaultInputDevice": "probes_device",
    "Pa_GetDefaultOutputDevice": "probes_device",
    "Pa_GetHostApiCount": "probes_device",
    "Pa_GetHostApiInfo": "probes_device",
    "Pa_GetDefaultHostApi": "probes_device",
    "Pa_HostApiDeviceIndexToDeviceIndex": "probes_device",
    "Pa_HostApiTypeIdToHostApiIndex": "probes_device",
    "Pa_GetSampleSize": "probes_device",
    # --- inert: no hardware contact -----------------------------------------
    "Pa_Sleep": "inert",
    "Pa_GetVersion": "inert",
    "Pa_GetVersionInfo": "inert",
    "Pa_GetVersionText": "inert",
    "Pa_GetErrorText": "inert",
    "Pa_GetLastHostErrorInfo": "inert",
    # --- host-API setup helpers: build a settings struct, open nothing -------
    "PaMacCore_SetupStreamInfo": "inert",
    "PaMacCore_SetupChannelMap": "inert",
    "PaAsio_GetAvailableLatencyValues": "probes_device",
    "PaAsio_ShowControlPanel": "probes_device",
}

#: PortAudio constants (``paClipOff``, ``paMME``, ...) are enum values, not
#: calls.  Referencing one cannot reach hardware, so they are inert by rule.
#: PortAudio's own convention is the discriminator: ``pa`` + capital, no
#: underscore == constant; ``Pa_`` / ``PaHostApi_`` == function.
def _is_constant(symbol: str) -> bool:
    return (
        symbol.startswith("pa")
        and len(symbol) > 2
        and symbol[2].isupper()
    )

SEVERITY_ORDER = ["inert", "probes_device", "opens_device"]


def _worst(classes: Iterable[str]) -> str:
    worst = "inert"
    for c in classes:
        if SEVERITY_ORDER.index(c) > SEVERITY_ORDER.index(worst):
            worst = c
    return worst


class _Scanner(ast.NodeVisitor):
    """Collect, per function, the ``_lib.Pa_*`` symbols and callees it names."""

    def __init__(self) -> None:
        self.pa_refs: Dict[str, Set[str]] = {}
        self.callees: Dict[str, Set[str]] = {}
        self.class_bases: Dict[str, List[str]] = {}
        self._scope: List[str] = []

    # -- scope bookkeeping --------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_bases[node.name] = [
            b.id for b in node.bases if isinstance(b, ast.Name)
        ]
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def _visit_func(self, node) -> None:
        qual = ".".join(self._scope + [node.name])
        self.pa_refs.setdefault(qual, set())
        self.callees.setdefault(qual, set())
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    # -- the two things we actually care about ------------------------------
    def visit_Attribute(self, node: ast.Attribute) -> None:
        # `_lib.Pa_OpenStream` -> Attribute(value=Name('_lib'), attr='Pa_...')
        if isinstance(node.value, ast.Name) and node.value.id == "_lib":
            for enclosing in self._enclosing_functions():
                self.pa_refs.setdefault(enclosing, set()).add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = self._call_name(node.func)
        if name:
            for enclosing in self._enclosing_functions():
                self.callees.setdefault(enclosing, set()).add(name)
        self.generic_visit(node)

    # -- helpers ------------------------------------------------------------
    def _enclosing_functions(self) -> List[str]:
        """Every function scope we are lexically inside, innermost outward.

        A nested/closure function's PortAudio contact belongs to its parent too:
        sounddevice defines the stream callbacks and helpers inline, and a
        closure only runs because its parent made it run.
        """
        out = []
        for i in range(len(self._scope), 0, -1):
            qual = ".".join(self._scope[:i])
            if qual in self.pa_refs or qual in self.callees:
                out.append(qual)
        return out

    @staticmethod
    def _call_name(func: ast.expr):
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None


def _resolve(name: str, known: Set[str]) -> Set[str]:
    """Map a bare callee name onto every known qualified function matching it.

    A bare name in the source (``wait(...)``, ``self.stream.close(...)``) is
    ambiguous: AST cannot tell which definition it lands on.  So resolution is
    deliberately over-approximate — EVERY definition whose last segment matches
    is a candidate, module-level function *and* class method alike.

    ⚠️ It used to short-circuit: ``if name in known: return {name}``.  That is a
    silent false-negative generator, and it produced one — ``sounddevice.wait``.
    A module-level ``wait()`` exists, so the callee ``_last_callback.wait(...)``
    inside it resolved to the module function (itself) and STOPPED, never
    reaching ``_CallbackContext.wait``, which calls ``self.stream.close()`` and
    so reaches ``Pa_CloseStream``.  ``wait`` was therefore classified ``inert``
    and left unguarded.  Whenever a method shares a name with a module-level
    function, the short-circuit hid the method's PortAudio reachability.

    Over-approximating costs at worst an extra guarded entry point; the
    short-circuit cost an unguarded device-touching one.  On a task whose
    acceptance rejects whitelists, the asymmetry decides it.
    """
    return {k for k in known if k.split(".")[-1] == name} | ({name} if name in known else set())


def _classify_symbols(symbols: Iterable[str], unclassified: Set[str]) -> str:
    """Severity of a symbol set, applying the constant rule and the fail-safe."""
    classes = []
    for sym in symbols:
        if _is_constant(sym):
            classes.append("inert")
            continue
        sev = PA_SEVERITY.get(sym)
        if sev is None:
            unclassified.add(sym)
            sev = "opens_device"  # fail-safe
        classes.append(sev)
    return _worst(classes) if classes else "inert"


def _reach_fixpoint(scanner: _Scanner, known: Set[str], block: Set[str]) -> Dict[str, Set[str]]:
    """Transitive closure of PortAudio references over the call graph.

    ``block`` names call targets that propagation stops at.  With an empty
    ``block`` this is plain reachability (used for classification).  With the
    public entry points blocked it yields *unmediated* reachability: only the
    crossings this node reaches WITHOUT going through a door the instrument
    already guards.  See WHERE THE GUARD GOES in the module docstring.
    """
    reach: Dict[str, Set[str]] = {k: set(v) for k, v in scanner.pa_refs.items()}
    for k in known:
        reach.setdefault(k, set())
    changed = True
    while changed:
        changed = False
        for fn in known:
            for callee in scanner.callees.get(fn, ()):
                for target in _resolve(callee, known):
                    if target in block and target != fn:
                        continue
                    new = reach.get(target, set()) - reach[fn]
                    if new:
                        reach[fn] |= new
                        changed = True
    return reach


def analyse(module) -> dict:
    source = inspect.getsource(module)
    tree = ast.parse(source)
    scanner = _Scanner()
    scanner.visit(tree)

    known = set(scanner.pa_refs) | set(scanner.callees)

    # Inherited methods: a subclass method resolution is approximated by giving
    # each class its bases' methods (single-file module, shallow hierarchy).
    for cls, bases in scanner.class_bases.items():
        for base in bases:
            for qual in list(known):
                if qual.startswith(base + "."):
                    tail = qual[len(base) + 1 :]
                    inherited = f"{cls}.{tail}"
                    if inherited not in known:
                        scanner.callees.setdefault(inherited, set()).add(qual)
                        scanner.pa_refs.setdefault(inherited, set())
                        known.add(inherited)

    # Public entry points, taken from the live module object (not a name list).
    public_names = [n for n in dir(module) if not n.startswith("_")]
    public_functions = {
        n for n in public_names
        if callable(getattr(module, n)) and not inspect.isclass(getattr(module, n))
    }

    # Two closures: plain reachability decides the CLASSIFICATION; unmediated
    # reachability (blocked at the public doors the instrument already guards)
    # decides WHERE THE GUARD GOES.
    reach = _reach_fixpoint(scanner, known, block=set())
    unmediated = _reach_fixpoint(scanner, known, block=public_functions)

    entry_points = {}
    unclassified: Set[str] = set()
    for name in sorted(public_names):
        obj = getattr(module, name)
        if inspect.isclass(obj):
            quals = [q for q in known if q.split(".")[0] == name]
            kind = "class"
        elif callable(obj):
            quals = list(_resolve(name, known))
            kind = "function"
        else:
            entry_points[name] = {
                "kind": type(obj).__name__,
                "classification": "not_callable",
                "portaudio_symbols": [],
                "via": [],
                "guard_targets": {},
                "mediated_by": [],
            }
            continue

        symbols: Set[str] = set()
        for q in quals:
            symbols |= reach.get(q, set())
        classification = _classify_symbols(symbols, unclassified)

        # Where does the guard go?  For a function, on the function itself.  For
        # a class, on each method whose OWN unmediated reach is device-touching
        # -- never a blanket __init__, which is how `PortAudioError.__init__`
        # (absent from the call graph entirely) came to be guarded while
        # `PortAudioError.__str__` (the method that actually reaches PortAudio)
        # did not.
        guard_targets: Dict[str, str] = {}
        mediated_by: Set[str] = set()
        if kind == "function":
            if classification in ("opens_device", "probes_device"):
                guard_targets[name] = classification
        else:
            for q in quals:
                tail = q[len(name) + 1:]
                if "." in tail:  # a closure inside a method, not addressable
                    continue
                own = _classify_symbols(unmediated.get(q, set()), unclassified)
                if own in ("opens_device", "probes_device"):
                    guard_targets[tail] = own
            if not guard_targets and classification in ("opens_device", "probes_device"):
                # Device-touching, but every route runs through a public entry
                # point that is itself guarded.  Name the mediators so this is
                # an audited decision rather than a silent gap.
                for q in quals:
                    for callee in scanner.callees.get(q, ()):
                        if callee in public_functions:
                            mediated_by.add(callee)

        entry_points[name] = {
            "kind": kind,
            "classification": classification,
            "portaudio_symbols": sorted(symbols),
            "via": sorted(quals),
            "guard_targets": dict(sorted(guard_targets.items())),
            "mediated_by": sorted(mediated_by),
        }

    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "task": "VM-2072",
        "slice": "repro-001",
        "python": sys.version.split()[0],
        "sounddevice_version": getattr(module, "__version__", "unknown"),
        "sounddevice_file": getattr(module, "__file__", "unknown"),
        "method": (
            "AST call-graph over the installed sounddevice source; each public "
            "entry point is classified by the most severe _lib.Pa_* symbol it "
            "can transitively reach. Unknown Pa_* symbols fail safe to "
            "opens_device."
        ),
        "unclassified_portaudio_symbols": sorted(unclassified),
        "entry_points": entry_points,
        "device_touching": sorted(
            n
            for n, e in entry_points.items()
            if e["classification"] in ("opens_device", "probes_device")
        ),
        "opens_device": sorted(
            n for n, e in entry_points.items() if e["classification"] == "opens_device"
        ),
        "probes_device": sorted(
            n for n, e in entry_points.items() if e["classification"] == "probes_device"
        ),
        "mediated": sorted(
            n for n, e in entry_points.items()
            if e["mediated_by"] and not e["guard_targets"]
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", metavar="PATH", help="write the full record here")
    args = ap.parse_args()

    import sounddevice  # imported late so --help works without the dependency

    report = analyse(sounddevice)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")

    print(f"sounddevice {report['sounddevice_version']} @ {report['sounddevice_file']}")
    print(f"python {report['python']}")
    print()
    print(f"opens_device  ({len(report['opens_device'])}): "
          f"{', '.join(report['opens_device'])}")
    print(f"probes_device ({len(report['probes_device'])}): "
          f"{', '.join(report['probes_device'])}")
    inert = [n for n, e in report["entry_points"].items()
             if e["classification"] == "inert"]
    print(f"inert         ({len(inert)}): {', '.join(sorted(inert))}")
    print()
    for name in report["device_touching"]:
        entry = report["entry_points"][name]
        if entry["kind"] != "class":
            continue
        if entry["guard_targets"]:
            print(f"guard targets  {name}: {', '.join(sorted(entry['guard_targets']))}")
        else:
            print(f"MEDIATED       {name}: no guard of its own; every route runs "
                  f"through {', '.join(entry['mediated_by'])}, which is guarded")
    if report["unclassified_portaudio_symbols"]:
        print()
        print("UNCLASSIFIED PortAudio symbols (treated as opens_device): "
              + ", ".join(report["unclassified_portaudio_symbols"]))
    if args.json:
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

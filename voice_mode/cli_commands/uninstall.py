"""``voicemode uninstall``: remove VoiceMode from this HOME, safely.

Shape (VM-2625 design.md):

- ``build_plan(ctx)`` is read-only. It computes every action from this
  HOME's own paths plus a few read-only probes (``launchctl print``,
  ``systemctl --user show``, ``uv tool dir``) and JSON reads.
- ``render(plan)`` prints it. ``--dry-run`` stops there.
- ``execute(plan, ctx)`` performs exactly the plan's actions and nothing else.
- ``remove_package(plan, ctx)`` runs ``uv tool uninstall voice-mode`` LAST.

Safety rules the code keeps (design section 5):

- Removal comes only from the plan, under an allowlist. Unknown entries are
  listed and left alone. Voice clones are never removed.
- No side effect is keyed on anything except this HOME's paths: a launchd or
  systemd unit is stopped only when the loaded job's file IS this HOME's unit
  file; ``uv`` and ``claude`` are called only when their state lives inside
  HOME. Nothing is ever killed by port. The keychain, shared caches, system
  packages, shell rc files and repo files are never touched.
- Every outside effect goes through ``ctx.run`` (the one seam), and the
  context is built once, by ``make_context()`` (the one CLI patch point).
- A probe that can't decide is an error: the item is skipped and the package
  is kept, so a re-run finishes the job.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

import click

from voice_mode.cli_commands.claude import is_any_voicemode_hook

# ---------------------------------------------------------------------------
# Policy tables
# ---------------------------------------------------------------------------

SOFTWARE = "software"   # removed by default
MODELS = "models"       # kept by default; --remove-models / --remove-all-data
CONFIG = "config"       # backed up by default; deleted by --remove-all-data
DATA = "data"           # kept by default; --remove-all-data
CLONES = "clones"       # never removed, under any flag

# Design Q1. Whisper and Kokoro keep their models INSIDE their installs, so
# keeping the models means keeping the whole install (keeping only
# services/whisper/models breaks a reinstall). The foreman's build is option
# (b): the installs are kept by default (their units are still removed) and
# --remove-models removes them. Option (a) -- remove them with the rest of the
# software -- is this one line: SERVICE_INSTALL_CLASS = SOFTWARE
SERVICE_INSTALL_CLASS = MODELS

# Entries under ~/.voicemode (and under VOICEMODE_BASE_DIR when it differs),
# by class. Anything not named here is "unknown": listed, never removed.
ENTRIES: dict[str, str] = {
    # software
    "services/whisper": SERVICE_INSTALL_CLASS,
    "services/kokoro": SERVICE_INSTALL_CLASS,
    "services/voicemode": SOFTWARE,
    "services/mlx-audio": SOFTWARE,
    "whisper.cpp": SOFTWARE,
    "kokoro-fastapi": SOFTWARE,
    "bin/voicemode-hook-receiver": SOFTWARE,
    "bin/voicemode-heard-hook": SOFTWARE,
    # config
    "voicemode.env": CONFIG,
    ".voicemode.env": CONFIG,
    # models in the data root
    "models": MODELS,
    "kokoro-models": MODELS,
    # data
    "audio": DATA,
    "transcriptions": DATA,
    "logs": DATA,
    "cache": DATA,
    "soundfonts": DATA,
    "state.json": DATA,
    "state": DATA,
    "conch": DATA,
    "conch.grant": DATA,
    "conch.queue.seq": DATA,
    "conch.queue.d": DATA,
    "control.sock": DATA,
    "focus-hold": DATA,
    "autofocus-disabled": DATA,
    "soundfonts-disabled": DATA,
    "music-library.db": DATA,
    "music-for-programming": DATA,
    "credentials": DATA,
    "credentials.migrated": DATA,
    "install.log": DATA,
    "config": DATA,
    "mouth": DATA,
    "whisper-server.log": DATA,
    "whisper-server.stdout.log": DATA,
    "whisper-server.stderr.log": DATA,
    "whisper-server.error.log": DATA,
    "kokoro.log": DATA,
    "kokoro.stdout.log": DATA,
    "kokoro.stderr.log": DATA,
    # voice clones
    "voices": CLONES,
    "voices.json": CLONES,
}
# Earlier config backups (voicemode.env.uninstalled, .uninstalled.<stamp>).
DATA_PREFIXES = ("voicemode.env.uninstalled", ".voicemode.env.uninstalled")
# Directories whose children are judged one by one; rmdir'd if left empty.
CONTAINERS = ("services", "bin")

# Services by their identifier; the on-disk stem comes from tools/service.py.
SERVICES = ("whisper", "kokoro", "voicemode", "mlx_audio")
MACOS_ONLY = {"mlx_audio"}
# Old voicemode label, still in voicemode's namespace, so it is planned.
MACOS_LEGACY_LABELS = ("com.voicemode.whisper-server",)
# Generic names an old voicemode wrote, but a user's own server can own too.
# Reported with the manual command, never touched (RF5, V1, C2).
MACOS_GENERIC_PLISTS = ("com.whisper.server.plist",)
LINUX_GENERIC_UNITS = ("kokoro-fastapi.service", "whisper-server.service")
LINUX_GENERIC_UNIT_RE = re.compile(r"^kokoro-fastapi-.+\.service$")

MCP_NAMES = ("voicemode", "voice-mode", "voice-mcp")

COMPLETION_ZSH = ".zfunc/_voicemode"
COMPLETION_FISH = ".config/fish/completions/voicemode.fish"
COMPLETION_BASH = ".bash_completion.d/voicemode"
BASH_STARTUP_FILES = (".bashrc", ".bash_profile", ".bash_login", ".profile",
                      ".bash_completion")
BASH_STARTUP_DIRS = (".bashrc.d",)

# Env vars that can put voicemode data outside the roots (design 2.6, C1).
CUSTOM_LOCATION_VARS = (
    "VOICEMODE_MODELS_DIR", "VOICEMODE_WHISPER_MODEL_PATH",
    "VOICEMODE_KOKORO_MODELS_DIR", "VOICEMODE_KOKORO_CACHE_DIR",
    "VOICEMODE_EVENT_LOG_DIR", "VOICEMODE_CONTROL_SOCKET",
    "VOICEMODE_VOICES_DIR", "VOICEMODE_MOUTH_DIR",
    "VOICEMODE_MOUTH_AUDIO_DIR", "VOICEMODE_MOUTH_SETTINGS",
    "VOICEMODE_MOUTH_MAILBOX",
)
HOME_ROOT_FILES = ("voicemode_debug.log", "voicemode_trace.log", "voicemode_logs")
HOME_ROOT_GLOBS = ("voice-mode-audio-*",)

PROBE_TIMEOUT = 30
DOCS = "docs/reference/uninstall.md (https://voice-mode.readthedocs.io)"


# ---------------------------------------------------------------------------
# Context: everything the plan reads from the outside world
# ---------------------------------------------------------------------------

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class Context:
    home: Path
    cwd: Path
    base_dir: Optional[Path]      # resolve_base(); None = not usable, report-only
    env: Mapping[str, str]
    system: str                   # "Darwin" | "Linux" | "Windows"
    uid: int
    run: Runner                   # run(argv, env=None) -> CompletedProcess; never raises
    sys_prefix: Path
    interactive: bool = False     # stdin is a TTY (C3)

    @property
    def vm(self) -> Path:
        return self.home / ".voicemode"


def make_runner(env: Mapping[str, str]) -> Runner:
    """A runner that never raises: missing tool -> 127, timeout -> 124.

    Tools are called by bare name, so PATH decides (the e2e shims rely on it).
    Every child gets ``env`` (the context's), so parent and child share HOME.
    """
    def run(argv: Sequence[str], env_override: Optional[Mapping[str, str]] = None,
            **_ignored) -> subprocess.CompletedProcess:
        child_env = dict(env_override if env_override is not None else env)
        try:
            return subprocess.run(list(argv), capture_output=True, text=True,
                                  timeout=PROBE_TIMEOUT, env=child_env)
        except FileNotFoundError as exc:
            return subprocess.CompletedProcess(list(argv), 127, "", str(exc))
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(list(argv), 124, "", "timed out")
        except OSError as exc:
            return subprocess.CompletedProcess(list(argv), 126, "", str(exc))
    return run


def make_context() -> Context:
    """The real context. The one patch point for CLI tests (RF10)."""
    home = Path.home()
    env = dict(os.environ)
    try:
        uid = os.getuid()
    except AttributeError:          # Windows
        uid = -1
    return Context(
        home=home,
        cwd=Path.cwd(),
        base_dir=resolve_base(env, home),
        env=env,
        system=platform.system(),
        uid=uid,
        run=make_runner(env),
        sys_prefix=Path(sys.prefix),
        interactive=sys.stdin.isatty(),
    )


_VAR_RE = re.compile(r"\$(\w+)|\$\{(\w+)\}")


def expand(raw: str, env: Mapping[str, str], home: Path) -> Optional[Path]:
    """Expand ``$VARS`` from ``env`` and a leading ``~`` to ``home``. Pure.

    Returns None when the result is not absolute, or has a ``..`` component
    (C5): neither can be trusted to name a place inside HOME.
    """
    def sub(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        return env.get(name, m.group(0))
    text = _VAR_RE.sub(sub, raw)
    if text == "~":
        path = home
    elif text.startswith("~/"):
        path = home / text[2:]
    else:
        path = Path(text)
    if not path.is_absolute() or ".." in path.parts:
        return None
    return path


def resolve_base(env: Mapping[str, str], home: Path) -> Optional[Path]:
    """``VOICEMODE_BASE_DIR`` from the context (V2). Empty counts as unset."""
    raw = env.get("VOICEMODE_BASE_DIR") or ""
    if not raw:
        return home / ".voicemode"
    return expand(raw, env, home)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _norm(p: Path) -> str:
    return os.path.normpath(os.path.abspath(str(p)))


def _strictly_inside(child: Path, parent: Path) -> bool:
    c, p = _norm(child), _norm(parent)
    return c != p and c.startswith(p.rstrip(os.sep) + os.sep)


def _real_inside(child: Path, parent: Path, *, allow_equal: bool = False) -> bool:
    c, p = os.path.realpath(child), os.path.realpath(parent)
    if allow_equal and c == p:
        return True
    return c.startswith(p.rstrip(os.sep) + os.sep)


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.realpath(a) == os.path.realpath(b)


def _lexists(p: Path) -> bool:
    return os.path.lexists(p)


def _tilde(p: Path, home: Path) -> str:
    s, h = str(p), str(home)
    if s == h:
        return "~"
    if s.startswith(h.rstrip(os.sep) + os.sep):
        return "~" + s[len(h.rstrip(os.sep)):]
    return s


def _size(p: Path) -> int:
    """Bytes under ``p``, not following symlinks."""
    try:
        if p.is_symlink() or not p.is_dir():
            return p.lstat().st_size
    except OSError:
        return 0
    total = 0
    for dirpath, _dirs, files in os.walk(p):
        for name in files:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def _read_json(path: Path) -> tuple[Optional[dict], Optional[str]]:
    """(data, error). A missing file is (None, None)."""
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return None, f"could not read {path}: {exc}"
    if not isinstance(data, dict):
        return None, f"could not read {path}: not a JSON object"
    return data, None


def _which(name: str, ctx: Context) -> Optional[str]:
    return shutil.which(name, path=ctx.env.get("PATH", ""))


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

@dataclass
class UnitStep:
    kind: str                      # "launchd" | "systemd"
    name: str                      # label, or unit file name
    path: Path                     # this HOME's unit file
    domains: list[str] = field(default_factory=list)   # launchd: gui/user to boot out
    disable: bool = False          # systemd: disable --now
    note: str = ""                 # e.g. "loaded from X, not touched"
    wants_link: Optional[Path] = None   # systemd enable link to unlink


@dataclass
class HookStep:
    path: Path                     # the file shown (may be a symlink)
    target: Path                   # the file written (the resolved target)
    removed: int
    events: list[str]


@dataclass
class PathStep:
    path: Path
    cls: str
    note: str = ""


@dataclass
class Plan:
    home: Path
    vm: Path
    base: Optional[Path]
    base_removable: bool
    dry_run_flags: tuple[bool, bool]          # (remove_models, remove_all_data)
    units: list[UnitStep] = field(default_factory=list)
    hooks: Optional[HookStep] = None
    mcp: list[str] = field(default_factory=list)
    removes: list[PathStep] = field(default_factory=list)
    backups: list[tuple[Path, Path]] = field(default_factory=list)
    rmdirs: list[Path] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)      # extra uv tools (mlx-audio)
    package: bool = False                               # uv tool uninstall voice-mode
    kept: list[tuple[Path, str]] = field(default_factory=list)
    report: list[str] = field(default_factory=list)     # left for you
    errors: list[str] = field(default_factory=list)
    allowed_roots: list[Path] = field(default_factory=list)
    allowed_exact: list[Path] = field(default_factory=list)

    @property
    def actions(self) -> int:
        return (len(self.units) + (1 if self.hooks else 0) + len(self.mcp)
                + len(self.removes) + len(self.backups) + len(self.tools)
                + (1 if self.package else 0))


def build_plan(ctx: Context, *, remove_models: bool = False,
               remove_all_data: bool = False) -> Plan:
    """Compute every action. Read-only: stat/lstat, JSON reads, read-only probes."""
    if remove_all_data:
        remove_models = True
    base = ctx.base_dir
    removable, base_reason = base_is_removable(ctx)
    plan = Plan(home=ctx.home, vm=ctx.vm, base=base, base_removable=removable,
                dry_run_flags=(remove_models, remove_all_data))
    plan.allowed_roots.append(ctx.vm)
    if removable and base is not None and _norm(base) != _norm(ctx.vm):
        plan.allowed_roots.append(base)

    _plan_units(plan, ctx)
    _plan_claude(plan, ctx)
    _plan_files(plan, ctx, remove_models, remove_all_data, base_reason)
    _plan_completions(plan, ctx)
    _plan_packages(plan, ctx)
    _plan_reports(plan, ctx)
    return plan


def base_is_removable(ctx: Context) -> tuple[bool, str]:
    """Design R3. Returns (removable, reason when not)."""
    base = ctx.base_dir
    if base is None:
        return False, "VOICEMODE_BASE_DIR is not an absolute path without '..'"
    if _norm(base) == _norm(ctx.vm):
        return True, ""
    if base.name not in (".voicemode", "voicemode"):
        return False, "its name is not .voicemode or voicemode"
    if not _strictly_inside(base, ctx.home):
        return False, "it is not inside your home directory"
    if project_config_sets_base(ctx):
        return False, "it was set by a project .voicemode.env"
    return True, ""


def project_config_sets_base(ctx: Context) -> bool:
    """Does the project config found from ``ctx.cwd`` set VOICEMODE_BASE_DIR?

    Same walk as config.find_voicemode_env_files(), over the context's cwd and
    home instead of the process's (V2). Errs towards True (report-only).
    """
    global_config = ctx.vm / "voicemode.env"
    current = ctx.cwd
    found: Optional[Path] = None
    while current != current.parent:
        standalone = current / ".voicemode.env"
        if standalone.exists():
            found = standalone
            break
        dir_file = current / ".voicemode" / "voicemode.env"
        if dir_file.exists() and _norm(dir_file) != _norm(global_config):
            found = dir_file
            break
        current = current.parent
    if found is None:
        return False
    try:
        lines = found.read_text().splitlines()
    except OSError:
        return True
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.split("=", 1)[0].strip() == "VOICEMODE_BASE_DIR":
            return True
    return False


# --- services ---------------------------------------------------------------

def _service_stem(service: str) -> str:
    # Imported here, not at module top: tools/service.py pulls in the MCP
    # server and every tool, which `voicemode --help` should not pay for.
    from voice_mode.tools.service import _service_file_name
    return _service_file_name(service)


def _plan_units(plan: Plan, ctx: Context) -> None:
    if ctx.system == "Darwin":
        _plan_launchd(plan, ctx)
    elif ctx.system == "Linux":
        _plan_systemd(plan, ctx)


def launchd_probe(ctx: Context, domain: str, label: str) -> tuple[str, Optional[str]]:
    """('loaded', path) | ('absent', None) | ('no-domain', None) | ('error', msg)."""
    target = f"{domain}/{ctx.uid}/{label}"
    res = ctx.run(["launchctl", "print", target])
    if res.returncode == 113:
        return "absent", None
    if res.returncode == 125:
        return "no-domain", None
    if res.returncode != 0:
        return "error", f"launchctl print {target} exited {res.returncode}"
    m = re.search(r"^\tpath = (.+)$", res.stdout or "", re.MULTILINE)
    if not m:
        return "error", f"launchctl print {target}: no 'path =' line to check"
    return "loaded", m.group(1).strip()


def _plan_launchd(plan: Plan, ctx: Context) -> None:
    agents = ctx.home / "Library" / "LaunchAgents"
    labels = [f"com.voicemode.{_service_stem(s)}" for s in SERVICES]
    labels += list(MACOS_LEGACY_LABELS)
    planned = set()
    for label in labels:
        plist = agents / f"{label}.plist"
        planned.add(plist.name)
        if not _lexists(plist):
            continue
        step = UnitStep("launchd", label, plist)
        failed = False
        others = []
        for domain in ("gui", "user"):
            state, detail = launchd_probe(ctx, domain, label)
            if state == "error":
                plan.errors.append(f"{label}: {detail}; not touched")
                failed = True
                break
            if state == "loaded":
                if _same_file(Path(detail), plist):
                    step.domains.append(domain)
                else:
                    others.append(detail)
        if failed:
            continue
        if others:
            step.note = f"loaded from {others[0]}, not touched"
        elif not step.domains:
            step.note = "not loaded"
        plan.units.append(step)
        plan.allowed_exact.append(plist)
    if agents.is_dir():
        for plist in sorted(agents.iterdir()):
            name = plist.name
            if name in planned:
                continue
            if name.startswith("com.voicemode.") and name.endswith(".plist") \
                    or name in MACOS_GENERIC_PLISTS:
                label = name[:-len(".plist")]
                plan.report.append(
                    f"launchd {label} ({_tilde(plist, ctx.home)}): not on VoiceMode's "
                    f"list, not touched. If it is VoiceMode's: launchctl bootout "
                    f"gui/{ctx.uid}/{label}; rm {_tilde(plist, ctx.home)}")


def systemd_probe(ctx: Context, unit: str) -> tuple[Optional[dict], Optional[str]]:
    res = ctx.run(["systemctl", "--user", "show", unit,
                   "-p", "FragmentPath", "-p", "LoadState", "-p", "ActiveState"])
    if res.returncode != 0:
        return None, f"systemctl --user show {unit} exited {res.returncode}"
    props = {}
    for line in (res.stdout or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    if "LoadState" not in props or "FragmentPath" not in props:
        return None, f"systemctl --user show {unit}: could not parse the output"
    return props, None


def _plan_systemd(plan: Plan, ctx: Context) -> None:
    unit_dir = ctx.home / ".config" / "systemd" / "user"
    wants = unit_dir / "default.target.wants"
    planned = set()
    for service in SERVICES:
        if service in MACOS_ONLY:
            continue
        unit = f"voicemode-{_service_stem(service)}.service"
        planned.add(unit)
        unit_file = unit_dir / unit
        if not _lexists(unit_file):
            continue
        props, err = systemd_probe(ctx, unit)
        if err:
            plan.errors.append(f"{unit}: {err}; not touched")
            continue
        step = UnitStep("systemd", unit, unit_file)
        frag = props.get("FragmentPath", "")
        if frag and _same_file(Path(frag), unit_file):
            step.disable = True
        elif frag:
            step.note = f"loaded from {frag}, not touched"
        else:
            step.note = "not loaded"
        link = wants / unit
        if link.is_symlink():
            if _link_points_at(link, unit_file):
                step.wants_link = link
                plan.allowed_exact.append(link)
            else:
                plan.report.append(f"{_tilde(link, ctx.home)} points elsewhere; not touched")
        plan.units.append(step)
        plan.allowed_exact.append(unit_file)
    if unit_dir.is_dir():
        for f in sorted(unit_dir.iterdir()):
            name = f.name
            if name in planned or not name.endswith(".service"):
                continue
            if name in LINUX_GENERIC_UNITS or LINUX_GENERIC_UNIT_RE.match(name) \
                    or name.startswith("voicemode-"):
                plan.report.append(
                    f"systemd {name} ({_tilde(f, ctx.home)}): not on VoiceMode's list, "
                    f"not touched. If it is VoiceMode's: systemctl --user disable --now "
                    f"{name}; rm {_tilde(f, ctx.home)}")


def _link_points_at(link: Path, target: Path) -> bool:
    try:
        dest = os.readlink(link)
    except OSError:
        return False
    dest_path = Path(dest)
    if not dest_path.is_absolute():
        dest_path = link.parent / dest_path
    return _norm(dest_path) == _norm(target) or _same_file(dest_path, target)


# --- Claude Code ------------------------------------------------------------

def claude_config_dir(ctx: Context) -> tuple[Optional[Path], bool]:
    """(dir holding .claude.json, inside HOME). CLAUDE_CONFIG_DIR wins (measured:
    with it set, Claude Code keeps .claude.json in that dir; else in HOME)."""
    raw = ctx.env.get("CLAUDE_CONFIG_DIR") or ""
    if not raw:
        return ctx.home, True
    path = expand(raw, ctx.env, ctx.home)
    if path is None:
        return None, False
    return path, _real_inside(path, ctx.home, allow_equal=True)


def strip_voicemode_handlers(settings: dict) -> tuple[dict, int, list[str]]:
    """Remove voicemode's hook handlers, one handler at a time (RF13).

    A matcher entry is dropped only when no handler is left in it; a foreign
    handler sharing an entry with voicemode's survives.
    """
    result = json.loads(json.dumps(settings))
    hooks = result.get("hooks")
    removed, events = 0, []
    if not isinstance(hooks, dict):
        return result, 0, []
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept_entries = []
        hit = False
        for entry in entries:
            handlers = entry.get("hooks", []) if isinstance(entry, dict) else []
            if not isinstance(handlers, list):
                kept_entries.append(entry)
                continue
            keep = [h for h in handlers
                    if not (isinstance(h, dict) and is_any_voicemode_hook({"hooks": [h]}))]
            n = len(handlers) - len(keep)
            if n:
                hit = True
                removed += n
                if keep:
                    entry = dict(entry)
                    entry["hooks"] = keep
                    kept_entries.append(entry)
            else:
                kept_entries.append(entry)
        if hit:
            events.append(event)
            if kept_entries:
                hooks[event] = kept_entries
            else:
                del hooks[event]
    if not hooks:
        result.pop("hooks", None)
    return result, removed, events


def _plan_claude(plan: Plan, ctx: Context) -> None:
    # Hooks: the path is computed from ctx.home, never claude.SETTINGS_PATHS.
    settings = ctx.home / ".claude" / "settings.json"
    if _lexists(settings):
        target = Path(os.path.realpath(settings))
        data, err = _read_json(target)
        if err:
            plan.errors.append(f"Claude settings: {err}")
        elif data is not None:
            _new, n, events = strip_voicemode_handlers(data)
            if n:
                if _real_inside(target, ctx.home):
                    plan.hooks = HookStep(settings, target, n, events)
                else:
                    plan.report.append(
                        f"{n} VoiceMode hook(s) in {target} (outside your home "
                        f"directory, via {_tilde(settings, ctx.home)}): remove them by hand "
                        f"or with `voicemode claude hooks remove` before uninstalling")
    for name in ("settings.json", "settings.local.json"):
        proj = ctx.cwd / ".claude" / name
        if not proj.exists() or (_lexists(settings) and _same_file(proj, settings)):
            continue
        data, _err = _read_json(proj)
        if data:
            _new, n, _ev = strip_voicemode_handlers(data)
            if n:
                plan.report.append(
                    f"{n} VoiceMode hook(s) in the project file {proj}: not touched "
                    f"(a repo file); remove them by hand")

    # MCP registrations, read from Claude's own config (never `claude mcp list`:
    # it health-checks, which starts every server).
    cfg_dir, inside = claude_config_dir(ctx)
    have_claude = _which("claude", ctx) is not None
    if cfg_dir is None:
        plan.report.append("CLAUDE_CONFIG_DIR is not an absolute path; MCP entries not "
                           "checked. Run: claude mcp remove voicemode -s user")
    else:
        cfg, err = _read_json(cfg_dir / ".claude.json")
        if err:
            plan.errors.append(f"Claude config: {err}")
            cfg = None
        cfg = cfg or {}
        servers = cfg.get("mcpServers") or {}
        user_names = [n for n in MCP_NAMES if isinstance(servers, dict) and n in servers]
        for n in user_names:
            if not inside:
                plan.report.append(
                    f"MCP server '{n}' in {cfg_dir / '.claude.json'} (CLAUDE_CONFIG_DIR is "
                    f"outside your home directory): claude mcp remove {n} -s user")
            elif not have_claude:
                plan.report.append(f"MCP server '{n}': `claude` not found on PATH; "
                                   f"when it is: claude mcp remove {n} -s user")
            else:
                plan.mcp.append(n)
        projects = cfg.get("projects") or {}
        if isinstance(projects, dict):
            for pdir, pdata in sorted(projects.items()):
                pservers = (pdata or {}).get("mcpServers") if isinstance(pdata, dict) else None
                if not isinstance(pservers, dict):
                    continue
                for n in MCP_NAMES:
                    if n in pservers:
                        plan.report.append(
                            f"local-scope MCP server '{n}' for {pdir}: "
                            f"cd {pdir} && claude mcp remove {n} -s local")

    # The plugin: read from files, never `claude plugin list --json`, which
    # writes ~/.claude.json and a backup (measured, Claude Code 2.1.330; C6).
    plugin_root = (cfg_dir / ".claude") if (cfg_dir is not None and
                                             _norm(cfg_dir) == _norm(ctx.home)) else cfg_dir
    ids: list[str] = []
    if plugin_root is not None:
        installed, _e = _read_json(plugin_root / "plugins" / "installed_plugins.json")
        for key in ((installed or {}).get("plugins") or {}):
            if isinstance(key, str) and key.startswith("voicemode@") and key not in ids:
                ids.append(key)
        sdata, _e = _read_json(plugin_root / "settings.json")
        for key in ((sdata or {}).get("enabledPlugins") or {}):
            if isinstance(key, str) and key.startswith("voicemode@") and key not in ids:
                ids.append(key)
    for pid in ids:
        plan.report.append(f"Claude Code plugin {pid}: claude plugin uninstall {pid}")


# --- files ------------------------------------------------------------------

def _classify(rel: str) -> Optional[str]:
    if rel in ENTRIES:
        return ENTRIES[rel]
    if any(rel.startswith(p) for p in DATA_PREFIXES):
        return DATA
    return None


def _decide(cls: str, remove_models: bool, remove_all_data: bool) -> str:
    """'remove' | 'backup' | 'keep'."""
    if cls == SOFTWARE:
        return "remove"
    if cls == MODELS:
        return "remove" if remove_models else "keep"
    if cls == CONFIG:
        return "remove" if remove_all_data else "backup"
    if cls == DATA:
        return "remove" if remove_all_data else "keep"
    return "keep"   # CLONES


def _backup_dest(src: Path, now: datetime) -> Path:
    dest = src.with_name(src.name + ".uninstalled")
    if not _lexists(dest):
        return dest
    stamp = now.strftime("%Y%m%d-%H%M%S")
    dest = src.with_name(f"{src.name}.uninstalled.{stamp}")
    n = 1
    while _lexists(dest):
        dest = src.with_name(f"{src.name}.uninstalled.{stamp}-{n}")
        n += 1
    return dest


def _root_entries(root: Path) -> list[tuple[str, Path]]:
    """(relative name, path) for top-level entries, and containers' children."""
    out: list[tuple[str, Path]] = []
    try:
        children = sorted(root.iterdir())
    except OSError:
        return out
    for child in children:
        if child.name in CONTAINERS and child.is_dir() and not child.is_symlink():
            try:
                for sub in sorted(child.iterdir()):
                    out.append((f"{child.name}/{sub.name}", sub))
            except OSError:
                pass
        else:
            out.append((child.name, child))
    return out


def _protected_paths(ctx: Context) -> list[Path]:
    """Voice clones living somewhere custom must survive any removal."""
    raw = ctx.env.get("VOICEMODE_VOICES_DIR") or ""
    p = expand(raw, ctx.env, ctx.home) if raw else None
    return [p] if p else []


def _plan_files(plan: Plan, ctx: Context, remove_models: bool,
                remove_all_data: bool, base_reason: str) -> None:
    roots = [ctx.vm]
    base = ctx.base_dir
    if base is not None and _norm(base) != _norm(ctx.vm):
        roots.append(base)
    elif base is None:
        raw = ctx.env.get("VOICEMODE_BASE_DIR", "")
        plan.report.append(f"VOICEMODE_BASE_DIR={raw!r}: {base_reason}; whatever "
                           f"VoiceMode wrote there is not touched")
    protected = _protected_paths(ctx)
    now = datetime.now()
    for root in roots:
        if not root.is_dir():
            continue
        root_ok = root in plan.allowed_roots
        if not root_ok:
            # A BASE that fails R3 may be HOME, / or any directory: say once why
            # it is skipped, and never list its unknown entries (they are not
            # VoiceMode's "kept data", just whatever else lives there).
            plan.report.append(f"VOICEMODE_BASE_DIR={root}: {base_reason}; VoiceMode's "
                               f"entries there are listed here and never touched")
        for rel, path in _root_entries(root):
            cls = _classify(rel)
            if cls is None:
                if root_ok:
                    plan.kept.append((path, "not created by VoiceMode, as far as this "
                                            "version knows"))
                continue
            action = _decide(cls, remove_models, remove_all_data)
            if action == "keep" and (root_ok or cls == CLONES):
                note = {CLONES: "voice clones: never removed",
                        MODELS: "models (--remove-models removes these)"}.get(cls, "")
                if cls == MODELS:
                    note += f", {_human(_size(path))}"
                plan.kept.append((path, note))
                continue
            if not root_ok:
                plan.report.append(
                    f"{path}: not touched, because VOICEMODE_BASE_DIR={root} "
                    f"({base_reason})")
                continue
            if any(_lexists(p) and (_norm(p) == _norm(path) or _strictly_inside(p, path))
                   for p in protected):
                plan.kept.append((path, "holds your voice clones (VOICEMODE_VOICES_DIR)"))
                continue
            if not _allowed(path, plan):
                plan.errors.append(f"{path}: resolves outside {root}; refused")
                continue
            if action == "backup":
                plan.backups.append((path, _backup_dest(path, now)))
            else:
                plan.removes.append(PathStep(path, cls))
        if root_ok:
            for c in CONTAINERS:
                plan.rmdirs.append(root / c)
            plan.rmdirs.append(root)
    # The VM root is removed last, after BASE.
    plan.rmdirs.sort(key=lambda p: (_norm(p) == _norm(ctx.vm), -len(p.parts)))


def _plan_completions(plan: Plan, ctx: Context) -> None:
    for rel in (COMPLETION_ZSH, COMPLETION_FISH):
        p = ctx.home / rel
        if _lexists(p) and not (p.is_dir() and not p.is_symlink()):
            plan.removes.append(PathStep(p, SOFTWARE, "shell completion"))
            plan.allowed_exact.append(p)
    bash = ctx.home / COMPLETION_BASH
    if not _lexists(bash) or (bash.is_dir() and not bash.is_symlink()):
        return
    mentions, unsure = bash_mentions(ctx)
    if mentions:
        for f in mentions:
            plan.report.append(f"bash completion {_tilde(bash, ctx.home)} is kept: "
                               f"{_tilde(f, ctx.home)} sources it. Delete that line, "
                               f"then the file")
    elif unsure:
        plan.report.append(f"bash completion {_tilde(bash, ctx.home)} is kept: could not "
                           f"read {_tilde(unsure[0], ctx.home)} to check it is not sourced")
    else:
        plan.removes.append(PathStep(bash, SOFTWARE, "shell completion"))
        plan.allowed_exact.append(bash)


def bash_mentions(ctx: Context) -> tuple[list[Path], list[Path]]:
    """(startup files naming the completion file, files that couldn't be read)."""
    candidates = [ctx.home / n for n in BASH_STARTUP_FILES]
    for d in BASH_STARTUP_DIRS:
        dd = ctx.home / d
        if dd.is_dir():
            try:
                candidates += sorted(p for p in dd.iterdir() if p.is_file())
            except OSError:
                return [], [dd]
    hits, unsure = [], []
    for f in candidates:
        if not f.exists():
            continue
        try:
            text = f.read_text(errors="replace")
        except OSError:
            unsure.append(f)
            continue
        if COMPLETION_BASH in text:
            hits.append(f)
    return hits, unsure


# --- packages ---------------------------------------------------------------

def _plan_packages(plan: Plan, ctx: Context) -> None:
    res = ctx.run(["uv", "tool", "dir"])
    if res.returncode == 127:
        plan.report.append("uv not found: if VoiceMode was installed with uv, run "
                           "`uv tool uninstall voice-mode` once uv is on PATH")
        return
    if res.returncode != 0 or not (res.stdout or "").strip():
        plan.errors.append(f"uv tool dir exited {res.returncode}; packages not touched")
        return
    tool_dir = Path(res.stdout.strip().splitlines()[-1])
    inside = _real_inside(tool_dir, ctx.home)
    vm_tool = tool_dir / "voice-mode"
    running_from_tool = _real_inside(ctx.sys_prefix, vm_tool, allow_equal=True)

    if not inside:
        if vm_tool.exists():
            plan.report.append(f"uv tool dir {tool_dir} is outside your home directory: "
                               f"run `uv tool uninstall voice-mode` yourself")
    elif vm_tool.exists() and running_from_tool:
        plan.package = True
    elif vm_tool.exists():
        plan.report.append(
            f"VoiceMode is running from {ctx.sys_prefix}, not the uv tool at "
            f"{_tilde(vm_tool, ctx.home)}: run `uv tool uninstall voice-mode` to remove "
            f"the tool too")
    if not running_from_tool:
        plan.report.append(
            f"This VoiceMode runs from {ctx.sys_prefix} (not a uv tool install): "
            f"remove it the way you installed it (pipx, a source checkout, ...)")

    mlx_tool = tool_dir / "mlx-audio"
    if mlx_tool.exists():
        evidence = any(_lexists(r / "services" / "mlx-audio")
                       for r in {ctx.vm, ctx.base_dir} if r is not None) \
            or _lexists(ctx.home / "Library" / "LaunchAgents" /
                        "com.voicemode.mlx-audio.plist")
        if inside and evidence:
            plan.tools.append("mlx-audio")
        else:
            plan.report.append("uv tool mlx-audio: no sign VoiceMode installed it, not "
                               "touched. If it is VoiceMode's: uv tool uninstall mlx-audio")


# --- left for you -----------------------------------------------------------

def _plan_reports(plan: Plan, ctx: Context) -> None:
    store = (ctx.env.get("VOICEMODE_CREDENTIAL_STORE") or "plaintext").lower()
    roots = [r for r in {ctx.vm, ctx.base_dir} if r is not None]
    if store == "keyring" or any(_lexists(r / "credentials.migrated") for r in roots):
        plan.report.append("VoiceMode Connect login in the OS keychain (service "
                           "'voicemode'): run `voicemode connect auth logout` BEFORE "
                           "uninstalling")
    else:
        for cred in sorted({r / "credentials" for r in roots if _lexists(r / "credentials")}):
            plan.report.append(f"VoiceMode Connect login: {_tilde(cred, ctx.home)} holds "
                               f"your tokens and is kept; run `voicemode connect auth "
                               f"logout` BEFORE uninstalling")
    for var in CUSTOM_LOCATION_VARS:
        raw = ctx.env.get(var) or ""
        if not raw:
            continue
        p = expand(raw, ctx.env, ctx.home)
        if p is None or not any(_norm(p) == _norm(r) or _strictly_inside(p, r)
                                for r in plan.allowed_roots):
            plan.report.append(f"{var}={raw}: a custom location, not touched")
    for name in HOME_ROOT_FILES:
        p = ctx.home / name
        if _lexists(p):
            plan.report.append(f"{_tilde(p, ctx.home)}: not touched (never deletes in "
                               f"your home directory itself)")
    for pattern in HOME_ROOT_GLOBS:
        for p in sorted(ctx.home.glob(pattern)):
            plan.report.append(f"{_tilde(p, ctx.home)}: not touched (never deletes in "
                               f"your home directory itself)")
    plan.report.append("Shared caches, never removed: Hugging Face hub (mlx-audio models); "
                       "uv cache (uv cache clean voice-mode)")
    plan.report.append(f"System packages (uv, Homebrew portaudio/ffmpeg/cmake, apt/dnf "
                       f"packages): see {DOCS}")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(plan: Plan, *, dry_run: bool) -> str:
    h = plan.home
    w = "would " if dry_run else ""
    out = []
    out.append("VoiceMode uninstall: DRY RUN, nothing will be changed." if dry_run
               else "VoiceMode uninstall: the plan.")
    data = str(plan.base) if plan.base is not None else "(VOICEMODE_BASE_DIR not usable)"
    out.append(f"home: {h}    data: {data}")
    if not plan.actions:
        out.append("")
        out.append("Nothing to remove.")
    if plan.units:
        out.append("")
        out.append("Services (stopped, then unregistered)")
        for u in plan.units:
            if u.kind == "launchd" and u.domains:
                verb = f"{w}stop + unregister  launchd {u.name} ({', '.join(u.domains)})"
            elif u.kind == "systemd" and u.disable:
                verb = f"{w}stop + disable  systemd {u.name}"
            else:
                verb = f"{w}remove the unit file only"
            line = f"  {verb}   {_tilde(u.path, h)}"
            if u.note:
                line += f"   ({u.note})"
            out.append(line)
            if u.wants_link:
                out.append(f"  {w}remove the enable link   {_tilde(u.wants_link, h)}")
    if plan.hooks or plan.mcp:
        out.append("")
        out.append("Claude Code")
        if plan.hooks:
            via = "" if plan.hooks.path == plan.hooks.target else \
                f" (through the link to {plan.hooks.target})"
            out.append(f"  {w}remove {plan.hooks.removed} VoiceMode hook handler(s) from "
                       f"{_tilde(plan.hooks.path, h)}{via}   ({', '.join(plan.hooks.events)})")
        for n in plan.mcp:
            out.append(f"  {w}run    claude mcp remove {n} -s user")
    if plan.removes or plan.backups:
        out.append("")
        out.append("Files")
        for s in plan.removes:
            note = f"    ({s.note or s.cls})"
            out.append(f"  {w}remove {_tilde(s.path, h)}{note}")
        for src, dst in plan.backups:
            out.append(f"  {w}back up {_tilde(src, h)} -> {dst.name}")
    if plan.tools or plan.package:
        out.append("")
        out.append("Packages")
        for t in plan.tools:
            out.append(f"  {w}run    uv tool uninstall {t}")
        if plan.package:
            out.append(f"  {w}run    uv tool uninstall voice-mode    (last)")
    if plan.kept:
        out.append("")
        rm, all_ = plan.dry_run_flags
        hint = "" if all_ else \
            " (--remove-all-data removes your data, never voice clones)"
        out.append(f"Kept{hint}")
        for p, note in plan.kept:
            out.append(f"  {_tilde(p, h)}" + (f"    {note}" if note else ""))
    if plan.report:
        out.append("")
        out.append("Left for you")
        for line in plan.report:
            out.append(f"  {line}")
    if plan.errors:
        out.append("")
        out.append("Problems (these items are skipped, and the voice-mode package is kept "
                   "so a re-run can finish)")
        for e in plan.errors:
            out.append(f"  {e}")
    if dry_run and plan.actions:
        out.append("")
        out.append("To do this: voicemode uninstall   (asks first), or add --yes")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

def _allowed(path: Path, plan: Plan) -> bool:
    """Design R2: strictly inside an allowed root (by the resolved parent), or an
    exact allowed path. Never a root itself."""
    parent = os.path.realpath(path.parent)
    for root in plan.allowed_roots:
        r = os.path.realpath(root)
        if _norm(path) == _norm(root) or os.path.realpath(path) == r:
            return False
        if parent == r or parent.startswith(r.rstrip(os.sep) + os.sep):
            return True
    for exact in plan.allowed_exact:
        if os.path.join(parent, path.name) == \
                os.path.join(os.path.realpath(exact.parent), exact.name):
            return True
    return False


def _safe_remove(path: Path, plan: Plan) -> Optional[str]:
    """Remove one planned path. Returns an error string, or None.

    A symlink is unlinked, never followed; rmtree never runs on a link.
    """
    if not _allowed(path, plan):
        return f"refused to remove {path}: outside VoiceMode's footprint"
    try:
        if path.is_symlink() or not path.is_dir():
            if _lexists(path):
                path.unlink()
        else:
            shutil.rmtree(path)
    except OSError as exc:
        return f"could not remove {path}: {exc}"
    return None


def _write_settings_atomic(target: Path, data: dict) -> None:
    """tmp + os.replace in the target's own directory, keeping its mode (V3)."""
    mode = target.stat().st_mode & 0o7777
    tmp = target.with_name(f".{target.name}.voicemode-uninstall.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.chmod(tmp, mode)
    os.replace(tmp, target)


def _claude(ctx: Context, *args: str) -> subprocess.CompletedProcess:
    """Every real claude call sets DISABLE_AUTOUPDATER=1 (C6)."""
    env = dict(ctx.env)
    env["DISABLE_AUTOUPDATER"] = "1"
    return ctx.run(["claude", *args], env)


def execute(plan: Plan, ctx: Context, *, echo: Callable[[str], None] = click.echo
            ) -> list[str]:
    """Perform the plan, except the voice-mode package. Returns errors."""
    errors: list[str] = list(plan.errors)

    # 1. Services first: every unit restarts on exit (KeepAlive/Restart=always).
    disabled_any = False
    for u in plan.units:
        if u.kind == "launchd":
            ok = True
            for domain in u.domains:
                state, detail = launchd_probe(ctx, domain, u.name)     # re-probe
                if state == "error":
                    errors.append(f"{u.name}: {detail}; left in place")
                    ok = False
                    continue
                if state != "loaded" or not _same_file(Path(detail), u.path):
                    continue
                res = ctx.run(["launchctl", "bootout", f"{domain}/{ctx.uid}/{u.name}"])
                if res.returncode != 0:
                    errors.append(f"launchctl bootout {domain}/{ctx.uid}/{u.name} exited "
                                  f"{res.returncode}; plist left in place")
                    ok = False
                else:
                    echo(f"stopped   launchd {u.name}")
            if not ok:
                continue
        else:
            if u.disable:
                props, err = systemd_probe(ctx, u.name)                # re-probe
                if err:
                    errors.append(f"{u.name}: {err}; left in place")
                    continue
                frag = props.get("FragmentPath", "")
                if frag and _same_file(Path(frag), u.path):
                    res = ctx.run(["systemctl", "--user", "disable", "--now", u.name])
                    if res.returncode != 0:
                        errors.append(f"systemctl --user disable --now {u.name} exited "
                                      f"{res.returncode}; unit file left in place")
                        continue
                    disabled_any = True
                    echo(f"stopped   systemd {u.name}")
        err = _safe_remove(u.path, plan)
        if err:
            errors.append(err)
        else:
            echo(f"removed   {_tilde(u.path, plan.home)}")
        if u.wants_link and u.wants_link.is_symlink():
            err = _safe_remove(u.wants_link, plan)
            if err:
                errors.append(err)
    if disabled_any:
        ctx.run(["systemctl", "--user", "daemon-reload"])
        ctx.run(["systemctl", "--user", "reset-failed"])

    # 2. Claude: hooks before files, so no hook points at a deleted script.
    if plan.hooks:
        try:
            data, err = _read_json(plan.hooks.target)
            if err or data is None:
                raise OSError(err or "file is gone")
            new, n, _events = strip_voicemode_handlers(data)
            if n:
                _write_settings_atomic(plan.hooks.target, new)
                echo(f"removed   {n} VoiceMode hook handler(s) from "
                     f"{_tilde(plan.hooks.path, plan.home)}")
        except OSError as exc:
            errors.append(f"Claude hooks not removed: {exc}")
    for name in plan.mcp:
        res = _claude(ctx, "mcp", "remove", name, "-s", "user")
        if res.returncode != 0:
            errors.append(f"claude mcp remove {name} -s user exited {res.returncode}: "
                          f"{(res.stderr or res.stdout or '').strip()[:200]}")
        else:
            echo(f"removed   MCP server {name} (user scope)")

    # 3. Files: software and completions, then config backups, then data.
    for s in plan.removes:
        if s.cls == SOFTWARE:
            _remove_step(s, plan, errors, echo)
    for src, dst in plan.backups:
        if _lexists(dst):
            errors.append(f"not backing up {src}: {dst} appeared meanwhile")
            continue
        try:
            os.rename(src, dst)
            echo(f"backed up {_tilde(src, plan.home)} -> {dst.name}")
        except OSError as exc:
            errors.append(f"could not back up {src}: {exc}")
    for s in plan.removes:
        if s.cls == CONFIG:
            _remove_step(s, plan, errors, echo)
    for s in plan.removes:
        if s.cls in (MODELS, DATA):
            _remove_step(s, plan, errors, echo)
    for d in plan.rmdirs:
        if d.is_dir() and not d.is_symlink():
            try:
                d.rmdir()
                echo(f"removed   {_tilde(d, plan.home)} (empty)")
            except OSError:
                pass

    # 4. VoiceMode's own mlx-audio uv tool (its unit is already gone).
    for tool in plan.tools:
        res = ctx.run(["uv", "tool", "uninstall", tool])
        if res.returncode != 0:
            errors.append(f"uv tool uninstall {tool} exited {res.returncode}")
        else:
            echo(f"removed   uv tool {tool}")
    return errors


def _remove_step(s: PathStep, plan: Plan, errors: list[str],
                 echo: Callable[[str], None]) -> None:
    if not _lexists(s.path):
        return
    err = _safe_remove(s.path, plan)
    if err:
        errors.append(err)
    else:
        echo(f"removed   {_tilde(s.path, plan.home)}")


def summary(plan: Plan, errors: list[str]) -> str:
    out = [""]
    if errors:
        out.append("Finished with problems:")
        out += [f"  {e}" for e in errors]
    else:
        out.append("Done.")
    if plan.kept:
        out.append(f"Kept {len(plan.kept)} item(s) under your data directory, listed "
                   f"above (voice clones are never removed).")
    if plan.report:
        out.append("See 'Left for you' above for the manual steps.")
    return "\n".join(out)


def remove_package(plan: Plan, ctx: Context, errors: list[str],
                   echo: Callable[[str], None] = click.echo) -> int:
    """The LAST step. Returns the exit code.

    `uv tool uninstall voice-mode` deletes the venv this interpreter runs from.
    NOTHING may import after it runs: every import this needs is at module top,
    and the only code after the call is one echo and the return.
    """
    if errors:
        if plan.package:
            echo("The voice-mode package was kept so you can re-run "
                 "`voicemode uninstall` to finish. Or remove it now: "
                 "uv tool uninstall voice-mode")
        return 1
    if not plan.package:
        return 0
    res = ctx.run(["uv", "tool", "uninstall", "voice-mode"])
    if res.returncode != 0:
        echo(f"uv tool uninstall voice-mode exited {res.returncode}; run it yourself.")
        return 1
    echo("Removed the voice-mode package. VoiceMode is uninstalled.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def refusal(ctx: Context) -> Optional[str]:
    if ctx.system == "Windows":
        return ("voicemode uninstall does not support Windows yet. "
                f"See {DOCS} for the manual steps.")
    if ctx.uid == 0:
        return ("Refusing to run as root: an uninstall under sudo could reach root's "
                "services and files. Run it as the user who installed VoiceMode.")
    env_home = ctx.env.get("HOME")
    if not env_home:
        return "Refusing: HOME is not set."
    if not _same_file(Path(env_home), ctx.home):
        return (f"Refusing: HOME ({env_home}) is not the home directory this process "
                f"resolved ({ctx.home}).")
    return None


_HELP = """Remove VoiceMode from this machine (this user's home directory).

\b
Prints the full plan first, then asks before removing anything.
  voicemode uninstall --dry-run    # show the plan, change nothing
  voicemode uninstall              # show the plan, then ask
  voicemode uninstall --yes        # show the plan, then proceed

\b
Removed by default: VoiceMode's services (stopped first), Claude Code hooks
and MCP registrations, ~/.voicemode/bin and services/voicemode, shell
completion files, and the voice-mode uv tool (last).
{q1}
Config (voicemode.env) is backed up to voicemode.env.uninstalled, never
overwriting an earlier backup.
Your data (audio, logs, transcriptions, models/) is kept and listed.
Voice clones (voices/, voices.json) are never removed, under any flag.
"""
# The Q1 sentence follows SERVICE_INSTALL_CLASS, so the policy flip stays one line.
_Q1_HELP = {
    MODELS: ("Whisper and Kokoro keep their models inside their installs, so those\n"
             "installs (~/.voicemode/services/whisper and services/kokoro) are KEPT by\n"
             "default with your models; --remove-models removes them."),
    SOFTWARE: ("Whisper and Kokoro keep their models inside their installs\n"
               "(~/.voicemode/services/whisper and services/kokoro), and those models are\n"
               "removed with the installs."),
}[SERVICE_INSTALL_CLASS]


@click.command("uninstall", help=_HELP.format(q1=_Q1_HELP))
@click.help_option("-h", "--help")
@click.option("--dry-run", is_flag=True,
              help="Print what would be removed, and change nothing.")
@click.option("-y", "--yes", is_flag=True,
              help="Proceed without asking (the plan is still printed).")
@click.option("--remove-models", is_flag=True,
              help="Also remove models: the Whisper and Kokoro installs and "
                   "~/.voicemode/models.")
@click.option("--remove-all-data", is_flag=True,
              help="Also remove all VoiceMode data and config, except voice clones "
                   "(voice clones are never removed). Implies --remove-models.")
def uninstall(dry_run: bool, yes: bool, remove_models: bool, remove_all_data: bool):
    ctx = make_context()
    reason = refusal(ctx)
    if reason:
        click.echo(reason, err=True)
        sys.exit(2)
    plan = build_plan(ctx, remove_models=remove_models, remove_all_data=remove_all_data)
    click.echo(render(plan, dry_run=dry_run))
    if dry_run:
        sys.exit(0)
    if not plan.actions:
        sys.exit(1 if plan.errors else 0)
    if not yes:
        if not ctx.interactive:
            click.echo("\nNot a terminal, so not asking. Re-run with --yes to proceed, "
                       "or --dry-run to only look.", err=True)
            sys.exit(2)
        click.echo("")
        if not click.confirm("Remove the items above?", default=False):
            click.echo("Nothing removed.")
            sys.exit(1)
    errors = execute(plan, ctx, echo=click.echo)
    click.echo(summary(plan, errors))
    sys.exit(remove_package(plan, ctx, errors, echo=click.echo))

"""Tests for ``voicemode uninstall`` (VM-2625, design.md section 8.1).

Isolation is by construction: every test builds a ``Context`` over a seeded
temp HOME with a fake runner. Nothing frozen at import is read, and an autouse
fixture makes ``subprocess.run``/``Popen`` RAISE, so the runner seam is the
only way out: a stray real ``uv`` or ``claude`` call fails the test instead of
reaching the developer's real tools and config.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

# Warm the lazy import now, before the no-subprocess fixture is armed.
import voice_mode.tools.service  # noqa: F401
from voice_mode.cli_commands import claude as claude_mod
from voice_mode.cli_commands import uninstall as un

UID = 502


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_subprocess(monkeypatch):
    def boom(*a, **k):
        raise AssertionError(f"real subprocess call in an uninstall test: {a!r}")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)


@pytest.fixture(autouse=True)
def pin_settings_paths(monkeypatch, tmp_path):
    # design 12 item 4: claude.SETTINGS_PATHS is frozen at import to the real
    # HOME. uninstall never uses it, but pin it so no test can reach it.
    pinned = tmp_path / "pinned-claude"
    monkeypatch.setattr(claude_mod, "SETTINGS_PATHS", {
        "user": pinned / "settings.json",
        "project": pinned / "p.json",
        "local": pinned / "l.json",
    })


def cp(argv, rc=0, out=""):
    return subprocess.CompletedProcess(list(argv), rc, out, "")


def launchd_loaded(path) -> tuple[int, str]:
    return 0, ("gui/502/com.voicemode.x = {\n\tactive count = 1\n"
               f"\tpath = {path}\n\tstate = running\n\tprogram = /x\n}}\n")


class FakeRunner:
    """Records every call; answers from ``responses`` (argv-prefix -> (rc, out)
    or callable(argv) -> (rc, out)), else from read-only defaults."""

    def __init__(self, home: Path, responses=None, timeline=None):
        self.home = home
        self.calls: list[tuple[list[str], dict | None]] = []
        self.responses = dict(responses or {})
        self.timeline = timeline if timeline is not None else []
        self.tool_dir = home / ".local" / "share" / "uv" / "tools"

    def __call__(self, argv, env=None):
        argv = list(argv)
        self.calls.append((argv, env))
        self.timeline.append(("run", tuple(argv)))
        for key, resp in self.responses.items():
            if tuple(argv[:len(key)]) == key:
                rc, out = resp(argv) if callable(resp) else resp
                return cp(argv, rc, out)
        if argv[:2] == ["launchctl", "print"]:
            return cp(argv, 113)
        if argv[:3] == ["systemctl", "--user", "show"]:
            return cp(argv, 0, "FragmentPath=\nLoadState=not-found\nActiveState=inactive\n")
        if argv[:3] == ["uv", "tool", "dir"]:
            return cp(argv, 0, f"{self.tool_dir}\n")
        return cp(argv, 0)

    def argvs(self):
        return [a for a, _ in self.calls]


def write(p: Path, text: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def make_ctx(home: Path, *, system="Darwin", env=None, runner=None, cwd=None,
             sys_prefix=None, interactive=False, uid=UID, base_dir="auto") -> un.Context:
    e = {"HOME": str(home), "PATH": str(home / "fakebin")}
    e.update(env or {})
    runner = runner or FakeRunner(home)
    return un.Context(
        home=home,
        cwd=cwd or home,
        base_dir=un.resolve_base(e, home) if base_dir == "auto" else base_dir,
        env=e,
        system=system,
        uid=uid,
        run=runner,
        sys_prefix=sys_prefix or (home / ".local/share/uv/tools/voice-mode"),
        interactive=interactive,
    )


VM_HOOK = {"type": "command", "command": "/h/.voicemode/bin/voicemode-hook-receiver || true"}
HEARD_HOOK = {"type": "command", "command": "'/h/.voicemode/bin/voicemode-heard-hook' hook || exit 1"}
FOREIGN_HOOK = {"type": "command", "command": "my-own-linter --fast"}


def settings_doc() -> dict:
    return {
        "theme": "dark",
        "hooks": {
            "PostToolUse": [{"matcher": "", "hooks": [VM_HOOK]}],
            "Stop": [{"matcher": "", "hooks": [VM_HOOK, FOREIGN_HOOK]}],    # mixed (RF13)
            "PreToolUse": [{"matcher": "Bash", "hooks": [FOREIGN_HOOK]}],
            "PostToolBatch": [{"hooks": [HEARD_HOOK]}],
        },
    }


def seed_footprint(home: Path, system: str = "Darwin") -> Path:
    """A full fake install (design 2), plus things that must survive."""
    vm = home / ".voicemode"
    write(vm / "services/whisper/build/bin/whisper-cli")
    write(vm / "services/whisper/models/ggml-base.bin", "model" * 100)
    write(vm / "services/kokoro/main.py")
    write(vm / "services/voicemode/start-voicemode-serve.sh")
    (vm / "services/mlx-audio").mkdir(parents=True)
    write(vm / "bin/voicemode-hook-receiver")
    write(vm / "bin/voicemode-heard-hook")
    write(vm / "whisper.cpp/main")
    write(vm / "voicemode.env", "OPENAI_API_KEY=secret\n")
    write(vm / "models/m.bin")
    write(vm / "kokoro-models/k.bin")
    write(vm / "audio/a.wav")
    write(vm / "transcriptions/t.txt")
    write(vm / "logs/conversations/x.jsonl")
    write(vm / "cache/c")
    write(vm / "soundfonts/default/x.sf2")
    write(vm / "state.json", "{}")
    write(vm / "conch")
    write(vm / "focus-hold")
    write(vm / "credentials", "token")
    write(vm / "mouth/settings.json")                 # C1
    write(vm / "voices/clone.wav")
    write(vm / "voices.json", "{}")
    write(vm / "my-notes.txt")                         # unknown
    if system == "Darwin":
        la = home / "Library/LaunchAgents"
        for stem in ("whisper", "kokoro", "serve", "mlx-audio", "whisper-server"):
            write(la / f"com.voicemode.{stem}.plist", f"<plist>{stem}</plist>")
        write(la / "com.voicemode.app.plist")           # foreign voicemode-suite app
        write(la / "com.whisper.server.plist")          # generic legacy (RF5)
    else:
        ud = home / ".config/systemd/user"
        wants = ud / "default.target.wants"
        wants.mkdir(parents=True)
        for stem in ("whisper", "kokoro", "serve"):
            unit = write(ud / f"voicemode-{stem}.service", f"[Unit]\n{stem}\n")
            os.symlink(unit, wants / unit.name)          # RF4
        for name in ("kokoro-fastapi.service", "whisper-server.service",
                     "kokoro-fastapi-8880.service", "voicemode-extra.service"):
            write(ud / name)
    write(home / "kokoro-fastapi/main.py")             # the user's own clone
    write(home / ".claude.json", json.dumps({
        "mcpServers": {"voicemode": {"command": "uvx"}, "voice-mode": {},
                       "other": {"command": "x"}},
        "projects": {"/work/proj": {"mcpServers": {"voicemode": {}}}},
    }))
    write(home / ".claude/settings.json", json.dumps(settings_doc(), indent=2))
    write(home / ".zfunc/_voicemode")
    write(home / ".config/fish/completions/voicemode.fish")
    write(home / ".bash_completion.d/voicemode")
    tools = home / ".local/share/uv/tools"
    write(tools / "voice-mode/bin/python")
    write(tools / "mlx-audio/bin/python")
    write(home / "fakebin/claude", "#!/bin/sh\n").chmod(0o755)
    return vm


def snapshot(root: Path) -> dict[str, tuple]:
    out = {}
    for dirpath, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(dirpath) / name
            rel = str(p.relative_to(root))
            if p.is_symlink():
                out[rel] = ("link", os.readlink(p))
            elif p.is_dir():
                out[rel] = ("dir",)
            else:
                data = p.read_bytes()
                out[rel] = ("file", len(data), hashlib.sha256(data).hexdigest(),
                            p.stat().st_mode & 0o777)
    return out


def rel(p: Path, home: Path) -> str:
    return str(p.relative_to(home))


def removed_paths(plan) -> set[str]:
    return {rel(s.path, plan.home) for s in plan.removes}


def kept_paths(plan) -> set[str]:
    return {rel(p, plan.home) for p, _ in plan.kept}


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "uhome"
    h.mkdir()
    return h


# ---------------------------------------------------------------------------
# Plan (pure)
# ---------------------------------------------------------------------------

def test_full_footprint_plan_darwin(home):
    seed_footprint(home)
    ctx = make_ctx(home)
    plan = un.build_plan(ctx)
    labels = {u.name for u in plan.units}
    assert labels == {"com.voicemode.whisper", "com.voicemode.kokoro", "com.voicemode.serve",
                      "com.voicemode.mlx-audio", "com.voicemode.whisper-server"}
    assert all(u.note == "not loaded" for u in plan.units)
    assert plan.hooks is not None and plan.hooks.removed == 3
    assert set(plan.hooks.events) == {"PostToolUse", "Stop", "PostToolBatch"}
    assert plan.mcp == ["voicemode", "voice-mode"]
    removes = removed_paths(plan)
    assert {".voicemode/services/voicemode", ".voicemode/services/mlx-audio",
            ".voicemode/bin/voicemode-hook-receiver", ".voicemode/bin/voicemode-heard-hook",
            ".voicemode/whisper.cpp", ".zfunc/_voicemode",
            ".config/fish/completions/voicemode.fish",
            ".bash_completion.d/voicemode"} == removes
    assert [(rel(s, home), d.name) for s, d in plan.backups] == \
        [(".voicemode/voicemode.env", "voicemode.env.uninstalled")]
    assert plan.package is True
    assert plan.tools == ["mlx-audio"]
    assert plan.errors == []
    text = un.render(plan, dry_run=True)
    assert "DRY RUN" in text and "claude plugin" not in text   # no plugin seeded


def test_empty_home_nothing_to_do(home):
    ctx = make_ctx(home, sys_prefix=home / "elsewhere")
    plan = un.build_plan(ctx)
    assert plan.actions == 0
    assert "Nothing to remove." in un.render(plan, dry_run=False)


@pytest.mark.parametrize("flags,removed,kept", [
    ({}, set(), {"services/whisper", "services/kokoro", "models", "kokoro-models",
                 "audio", "logs", "credentials", "mouth"}),
    ({"remove_models": True}, {"services/whisper", "services/kokoro", "models",
                               "kokoro-models"},
     {"audio", "logs", "credentials", "mouth", "state.json"}),
    ({"remove_all_data": True}, {"services/whisper", "services/kokoro", "models",
                                 "kokoro-models", "audio", "logs", "credentials", "mouth",
                                 "state.json", "voicemode.env"}, set()),
])
def test_data_policy_per_flags(home, flags, removed, kept):
    seed_footprint(home)
    plan = un.build_plan(make_ctx(home), **flags)
    r = {p.removeprefix(".voicemode/") for p in removed_paths(plan)}
    k = {p.removeprefix(".voicemode/") for p in kept_paths(plan)}
    assert removed <= r
    assert kept <= k
    assert not (removed & k)
    for clone in ("voices", "voices.json"):          # never, under any flag (R6)
        assert clone not in r
        assert clone in k
    assert "my-notes.txt" in k                         # unknown: kept (R4)
    if flags.get("remove_all_data"):
        assert plan.backups == []
    else:
        assert len(plan.backups) == 1


def test_q1_policy_is_one_constant():
    assert un.ENTRIES["services/whisper"] == un.SERVICE_INSTALL_CLASS
    assert un.ENTRIES["services/kokoro"] == un.SERVICE_INSTALL_CLASS
    assert un.SERVICE_INSTALL_CLASS == un.MODELS       # the foreman's build, option (b)


def test_kept_models_show_size(home):
    seed_footprint(home)
    plan = un.build_plan(make_ctx(home))
    notes = {rel(p, home): n for p, n in plan.kept}
    assert "--remove-models" in notes[".voicemode/services/whisper"]
    assert "KB" in notes[".voicemode/services/whisper"] or "B" in notes[".voicemode/services/whisper"]


# --- BASE (R3, RF2, V2, C5) -------------------------------------------------

def test_resolve_base_is_pure(home, monkeypatch):
    monkeypatch.setenv("HOME", "/nonexistent-real-home")
    monkeypatch.setenv("VOICEMODE_BASE_DIR", "/wrong")
    monkeypatch.setenv("X", "/wrong-x")
    env = {"HOME": str(home), "X": str(home / "xx")}
    assert un.resolve_base(env, home) == home / ".voicemode"
    assert un.resolve_base({**env, "VOICEMODE_BASE_DIR": ""}, home) == home / ".voicemode"
    assert un.resolve_base({**env, "VOICEMODE_BASE_DIR": "voicemode"}, home) is None
    assert un.resolve_base({**env, "VOICEMODE_BASE_DIR": "~user/.voicemode"}, home) is None
    assert un.resolve_base({**env, "VOICEMODE_BASE_DIR": "~/voicemode"}, home) == home / "voicemode"
    assert un.resolve_base({**env, "VOICEMODE_BASE_DIR": "$HOME/voicemode"}, home) == home / "voicemode"
    assert un.resolve_base({**env, "VOICEMODE_BASE_DIR": "${X}/voicemode"}, home) == home / "xx/voicemode"
    assert un.resolve_base({**env, "VOICEMODE_BASE_DIR": "~/link/../voicemode"}, home) is None  # C5


@pytest.mark.parametrize("base_of", [
    lambda h: h,                                 # HOME itself
    lambda h: Path("/"),
    lambda h: h.parent,                          # an ancestor of HOME
    lambda h: h / "data",                        # not named voicemode
    lambda h: h.parent / "voicemode",            # named voicemode, outside HOME
])
def test_base_report_only(home, base_of):
    seed_footprint(home)
    base = base_of(home)
    planted = None
    if base != Path("/"):
        planted = write(base / "audio" / "keep.wav")
    ctx = make_ctx(home, env={"VOICEMODE_BASE_DIR": str(base)}, cwd=home / "kokoro-fastapi")
    removable, _ = un.base_is_removable(ctx)
    assert removable is False
    plan = un.build_plan(ctx, remove_all_data=True)
    assert base not in plan.allowed_roots
    exact = {str(p) for p in plan.allowed_exact}
    for s in plan.removes:      # every removal is under ~/.voicemode, or an exact path
        assert un._strictly_inside(s.path, home / ".voicemode") or str(s.path) in exact, s.path
    if planted is not None and base != home:
        assert any(str(base / "audio") in line and "not touched" in line for line in plan.report)
        un.execute(plan, ctx, echo=lambda s: None)
        assert planted.exists()


def test_base_named_voicemode_inside_home_is_removable(home):
    base = home / "data" / "voicemode"
    write(base / "audio/a.wav")
    ctx = make_ctx(home, env={"VOICEMODE_BASE_DIR": str(base)})
    plan = un.build_plan(ctx, remove_all_data=True)
    assert base in plan.allowed_roots
    assert base / "audio" in {s.path for s in plan.removes}


def test_base_through_symlinked_ancestor_outside_home_is_report_only(home, tmp_path):
    """Check 2 is lexical; a BASE whose ancestor links outside HOME must still
    be report-only, or removals would land outside HOME (review O1)."""
    outside = tmp_path / "elsewhere"
    planted = write(outside / "voicemode" / "audio" / "keep.wav")
    os.symlink(outside, home / "link")
    base = home / "link" / "voicemode"
    ctx = make_ctx(home, env={"VOICEMODE_BASE_DIR": str(base)})
    removable, reason = un.base_is_removable(ctx)
    assert not removable and "symlink" in reason
    plan = un.build_plan(ctx, remove_all_data=True)
    assert base not in plan.allowed_roots
    assert not any(un._real_inside(s.path, outside) for s in plan.removes)
    un.execute(plan, ctx, echo=lambda s: None)
    assert planted.exists()


def test_base_through_symlinked_ancestor_inside_home_is_removable(home):
    real = home / "data"
    write(real / "voicemode" / "audio" / "a.wav")
    os.symlink(real, home / "link")
    ctx = make_ctx(home, env={"VOICEMODE_BASE_DIR": str(home / "link" / "voicemode")})
    assert un.base_is_removable(ctx) == (True, "")


def test_base_set_by_project_config_is_report_only(home):
    base = home / "data" / "voicemode"
    write(base / "audio/a.wav")
    proj = home / "work" / "repo"
    write(proj / ".voicemode.env", f"# comment\nVOICEMODE_BASE_DIR={base}\n")
    ctx = make_ctx(home, env={"VOICEMODE_BASE_DIR": str(base)}, cwd=proj / "sub")
    (proj / "sub").mkdir()
    removable, reason = un.base_is_removable(ctx)
    assert not removable and "project" in reason
    plan = un.build_plan(ctx, remove_all_data=True)
    assert base / "audio" not in {s.path for s in plan.removes}
    assert any(str(base / "audio") in line for line in plan.report)


def test_base_home_lists_no_unknowns_and_says_why(home):
    """A BASE that fails R3 (here HOME itself) is skipped with one reason line;
    whatever else lives there is never listed as VoiceMode's kept data."""
    seed_footprint(home)
    write(home / "Documents/taxes.pdf")
    write(home / "bin/mytool")
    write(home / "audio/a.wav")                     # a VoiceMode-shaped entry in BASE
    write(home / "voices/clone.wav")                # clones in BASE: still listed as kept
    ctx = make_ctx(home, env={"VOICEMODE_BASE_DIR": str(home)})
    plan = un.build_plan(ctx)
    kept = kept_paths(plan)
    assert "Documents" not in kept and "bin/mytool" not in kept and ".voicemode" not in kept
    assert "voices" in kept
    assert any(l.startswith(f"VOICEMODE_BASE_DIR={home}:") and "never touched" in l
               for l in plan.report)
    assert any(str(home / "audio") in l and "not touched" in l for l in plan.report)
    # ~/.voicemode itself is still handled as usual
    assert ".voicemode/my-notes.txt" in kept
    assert home / ".voicemode/services/voicemode" in {s.path for s in plan.removes}
    out = un.render(plan, dry_run=True)
    assert "~/Documents" not in out


def test_credentials_report_names_the_real_file(home):
    base = home / "data" / "voicemode"
    write(base / "credentials", "token")
    plan = un.build_plan(make_ctx(home, env={"VOICEMODE_BASE_DIR": str(base)}))
    assert any("~/data/voicemode/credentials" in l and "logout" in l for l in plan.report)


def test_relative_base_is_report_only(home):
    seed_footprint(home)
    ctx = make_ctx(home, env={"VOICEMODE_BASE_DIR": "voicemode-data"})
    assert ctx.base_dir is None
    plan = un.build_plan(ctx)
    assert any("VOICEMODE_BASE_DIR='voicemode-data'" in l for l in plan.report)
    # VM itself is still handled
    assert home / ".voicemode/services/voicemode" in {s.path for s in plan.removes}


# --- unknowns and off-list units (R4, RF5, V1, C2) --------------------------

def test_offlist_launchd_units_reported_not_planned(home):
    seed_footprint(home)
    plan = un.build_plan(make_ctx(home))
    assert "com.voicemode.app" not in {u.name for u in plan.units}
    assert any("com.voicemode.app" in l and "not touched" in l for l in plan.report)
    assert any("com.whisper.server" in l and "not touched" in l for l in plan.report)


def test_linux_generic_and_offlist_units_report_only_even_if_fragment_matches(home):
    seed_footprint(home, "Linux")
    ud = home / ".config/systemd/user"

    def show(argv):
        return 0, f"FragmentPath={ud / argv[3]}\nLoadState=loaded\nActiveState=active\n"
    runner = FakeRunner(home, {("systemctl", "--user", "show"): show})
    ctx = make_ctx(home, system="Linux", runner=runner)
    plan = un.build_plan(ctx)
    assert {u.name for u in plan.units} == {"voicemode-whisper.service",
                                           "voicemode-kokoro.service",
                                           "voicemode-serve.service"}
    for name in ("kokoro-fastapi.service", "whisper-server.service",
                 "kokoro-fastapi-8880.service", "voicemode-extra.service"):
        assert any(name in l and "not touched" in l for l in plan.report), name
        assert ud / name not in plan.allowed_exact
    un.execute(plan, ctx, echo=lambda s: None)
    for name in ("kokoro-fastapi.service", "whisper-server.service",
                 "kokoro-fastapi-8880.service", "voicemode-extra.service"):
        assert (ud / name).exists()
    disables = [a for a in runner.argvs() if a[:3] == ["systemctl", "--user", "disable"]]
    assert sorted(a[-1] for a in disables) == ["voicemode-kokoro.service",
                                               "voicemode-serve.service",
                                               "voicemode-whisper.service"]


# --- launchd guard (RF3) ----------------------------------------------------

def _darwin_whisper_only(home):
    plist = write(home / "Library/LaunchAgents/com.voicemode.whisper.plist", "<plist/>")
    return plist


def test_launchd_loaded_from_same_path_boots_out(home):
    plist = _darwin_whisper_only(home)
    runner = FakeRunner(home, {("launchctl", "print", f"gui/{UID}/com.voicemode.whisper"):
                               launchd_loaded(plist)})
    ctx = make_ctx(home, runner=runner)
    plan = un.build_plan(ctx)
    assert plan.units[0].domains == ["gui"]
    un.execute(plan, ctx, echo=lambda s: None)
    assert ["launchctl", "bootout", f"gui/{UID}/com.voicemode.whisper"] in runner.argvs()
    assert not plist.exists()


def test_launchd_same_file_other_spelling(home, tmp_path):
    _darwin_whisper_only(home)
    alias = tmp_path / "alias-home"
    os.symlink(home, alias)
    other_spelling = alias / "Library/LaunchAgents/com.voicemode.whisper.plist"
    runner = FakeRunner(home, {("launchctl", "print", f"gui/{UID}/com.voicemode.whisper"):
                               launchd_loaded(other_spelling)})
    plan = un.build_plan(make_ctx(home, runner=runner))
    assert plan.units[0].domains == ["gui"]


def test_launchd_loaded_from_other_path_skipped_file_removed(home, tmp_path):
    plist = _darwin_whisper_only(home)
    live = write(tmp_path / "realhome/Library/LaunchAgents/com.voicemode.whisper.plist")
    runner = FakeRunner(home, {("launchctl", "print", f"gui/{UID}/com.voicemode.whisper"):
                               launchd_loaded(live)})
    ctx = make_ctx(home, runner=runner)
    plan = un.build_plan(ctx)
    assert plan.units[0].domains == [] and str(live) in plan.units[0].note
    un.execute(plan, ctx, echo=lambda s: None)
    assert not any(a[:2] == ["launchctl", "bootout"] for a in runner.argvs())
    assert not plist.exists() and live.exists()


def test_launchd_not_loaded_file_only(home):
    plist = _darwin_whisper_only(home)
    runner = FakeRunner(home)
    ctx = make_ctx(home, runner=runner)
    plan = un.build_plan(ctx)
    un.execute(plan, ctx, echo=lambda s: None)
    assert not any(a[:2] == ["launchctl", "bootout"] for a in runner.argvs())
    assert not plist.exists()


def test_launchd_loaded_in_user_domain_only(home):
    plist = _darwin_whisper_only(home)
    runner = FakeRunner(home, {
        ("launchctl", "print", f"gui/{UID}/com.voicemode.whisper"): (113, ""),
        ("launchctl", "print", f"user/{UID}/com.voicemode.whisper"): launchd_loaded(plist),
    })
    ctx = make_ctx(home, runner=runner)
    plan = un.build_plan(ctx)
    assert plan.units[0].domains == ["user"]
    un.execute(plan, ctx, echo=lambda s: None)
    assert ["launchctl", "bootout", f"user/{UID}/com.voicemode.whisper"] in runner.argvs()


def test_launchd_domain_absent_is_skipped(home):
    _darwin_whisper_only(home)
    runner = FakeRunner(home, {("launchctl", "print", f"gui/{UID}"): (125, "")})
    plan = un.build_plan(make_ctx(home, runner=runner))
    assert plan.errors == [] and plan.units[0].domains == []


def test_launchd_unparseable_is_error_and_keeps_package(home):
    plist = _darwin_whisper_only(home)
    write(home / ".local/share/uv/tools/voice-mode/bin/python")
    runner = FakeRunner(home, {("launchctl", "print"): (0, "something unexpected")})
    ctx = make_ctx(home, runner=runner)
    plan = un.build_plan(ctx)
    assert plan.units == [] and plan.errors
    errors = un.execute(plan, ctx, echo=lambda s: None)
    assert plist.exists()
    assert un.remove_package(plan, ctx, errors, echo=lambda s: None) == 1
    assert ["uv", "tool", "uninstall", "voice-mode"] not in runner.argvs()


# --- systemd guard ----------------------------------------------------------

def _linux_whisper_only(home):
    ud = home / ".config/systemd/user"
    unit = write(ud / "voicemode-whisper.service")
    (ud / "default.target.wants").mkdir()
    link = ud / "default.target.wants/voicemode-whisper.service"
    os.symlink(unit, link)
    return unit, link


def test_systemd_fragment_equal_disables_and_reloads(home):
    unit, link = _linux_whisper_only(home)
    runner = FakeRunner(home, {("systemctl", "--user", "show"):
                               (0, f"FragmentPath={unit}\nLoadState=loaded\nActiveState=active\n")})
    ctx = make_ctx(home, system="Linux", runner=runner)
    plan = un.build_plan(ctx)
    assert plan.units[0].disable
    un.execute(plan, ctx, echo=lambda s: None)
    argvs = runner.argvs()
    assert ["systemctl", "--user", "disable", "--now", "voicemode-whisper.service"] in argvs
    assert ["systemctl", "--user", "daemon-reload"] in argvs
    assert not unit.exists() and not os.path.lexists(link)


def test_systemd_fragment_different_skips_no_reload(home, tmp_path):
    unit, link = _linux_whisper_only(home)
    other = write(tmp_path / "real/.config/systemd/user/voicemode-whisper.service")
    runner = FakeRunner(home, {("systemctl", "--user", "show"):
                               (0, f"FragmentPath={other}\nLoadState=loaded\nActiveState=active\n")})
    ctx = make_ctx(home, system="Linux", runner=runner)
    plan = un.build_plan(ctx)
    un.execute(plan, ctx, echo=lambda s: None)
    argvs = runner.argvs()
    assert not any(a[:3] == ["systemctl", "--user", "disable"] for a in argvs)
    assert ["systemctl", "--user", "daemon-reload"] not in argvs
    assert not unit.exists() and not os.path.lexists(link)    # file-only + its link
    assert other.exists()


def test_systemd_bus_unreachable_is_error(home):
    unit, _ = _linux_whisper_only(home)
    runner = FakeRunner(home, {("systemctl", "--user", "show"): (1, "")})
    plan = un.build_plan(make_ctx(home, system="Linux", runner=runner))
    assert plan.errors and plan.units == []


def test_systemd_wants_link_elsewhere_left(home, tmp_path):
    ud = home / ".config/systemd/user"
    write(ud / "voicemode-whisper.service")
    (ud / "default.target.wants").mkdir()
    other = write(tmp_path / "elsewhere.service")
    link = ud / "default.target.wants/voicemode-whisper.service"
    os.symlink(other, link)
    ctx = make_ctx(home, system="Linux")
    plan = un.build_plan(ctx)
    assert plan.units[0].wants_link is None
    un.execute(plan, ctx, echo=lambda s: None)
    assert os.path.lexists(link) and other.exists()


# --- uv guard ---------------------------------------------------------------

def test_uv_tool_dir_inside_home_plans_package(home):
    write(home / ".local/share/uv/tools/voice-mode/bin/python")
    plan = un.build_plan(make_ctx(home))
    assert plan.package


def test_uv_tool_dir_outside_home_reports(home, tmp_path):
    outside = tmp_path / "shared-tools"
    write(outside / "voice-mode/bin/python")
    runner = FakeRunner(home, {("uv", "tool", "dir"): (0, f"{outside}\n")})
    plan = un.build_plan(make_ctx(home, runner=runner, env={"UV_TOOL_DIR": str(outside)},
                                  sys_prefix=outside / "voice-mode"))
    assert not plan.package
    assert any("outside your home" in l for l in plan.report)


def test_no_uv_manual_step(home):
    runner = FakeRunner(home, {("uv",): (127, "")})
    plan = un.build_plan(make_ctx(home, runner=runner))
    assert not plan.package
    assert any("uv not found" in l for l in plan.report)


def test_other_install_method_reported(home):
    write(home / ".local/share/uv/tools/voice-mode/bin/python")
    plan = un.build_plan(make_ctx(home, sys_prefix=home / "src/voicemode/.venv"))
    assert not plan.package
    assert any("not a uv tool install" in l for l in plan.report)
    # One line, naming the separate uv tool, not two near-duplicates (O3).
    lines = [l for l in plan.report if str(home / "src/voicemode/.venv") in l]
    assert len(lines) == 1
    assert "uv tool uninstall voice-mode" in lines[0]


def test_other_install_method_without_uv_tool_names_no_uv_step(home):
    plan = un.build_plan(make_ctx(home, sys_prefix=home / "src/voicemode/.venv"))
    lines = [l for l in plan.report if "not a uv tool install" in l]
    assert len(lines) == 1 and "uv tool uninstall" not in lines[0]


def test_mlx_audio_tool_only_with_marker(home):
    write(home / ".local/share/uv/tools/mlx-audio/bin/python")
    plan = un.build_plan(make_ctx(home))
    assert plan.tools == []
    assert any("mlx-audio" in l and "not touched" in l for l in plan.report)
    (home / ".voicemode/services/mlx-audio").mkdir(parents=True)
    assert un.build_plan(make_ctx(home)).tools == ["mlx-audio"]


# --- Claude -----------------------------------------------------------------

def test_claude_config_dir_outside_home_report_only(home, tmp_path):
    cfg = tmp_path / "claude-cfg"
    write(cfg / ".claude.json", json.dumps({"mcpServers": {"voicemode": {}}}))
    write(home / "fakebin/claude").chmod(0o755)
    plan = un.build_plan(make_ctx(home, env={"CLAUDE_CONFIG_DIR": str(cfg)}))
    assert plan.mcp == []
    assert any("CLAUDE_CONFIG_DIR is outside" in l for l in plan.report)


def test_claude_config_dir_inside_home_used(home):
    cfg = home / ".claude-alt"
    write(cfg / ".claude.json", json.dumps({"mcpServers": {"voice-mcp": {}}}))
    write(home / "fakebin/claude").chmod(0o755)
    plan = un.build_plan(make_ctx(home, env={"CLAUDE_CONFIG_DIR": str(cfg)}))
    assert plan.mcp == ["voice-mcp"]


def test_mcp_steps_are_user_scoped_and_local_scope_reported(home):
    seed_footprint(home)
    runner = FakeRunner(home)
    ctx = make_ctx(home, runner=runner)
    plan = un.build_plan(ctx)
    assert any("cd /work/proj && claude mcp remove voicemode -s local" in l for l in plan.report)
    un.execute(plan, ctx, echo=lambda s: None)
    mcp_calls = [(a, e) for a, e in runner.calls if a[:3] == ["claude", "mcp", "remove"]]
    assert [a for a, _ in mcp_calls] == [
        ["claude", "mcp", "remove", "voicemode", "-s", "user"],
        ["claude", "mcp", "remove", "voice-mode", "-s", "user"],
    ]
    # C6: every real claude call sets DISABLE_AUTOUPDATER=1, and keeps HOME.
    for _a, env in mcp_calls:
        assert env["DISABLE_AUTOUPDATER"] == "1" and env["HOME"] == str(home)


def test_no_claude_on_path_manual_lines(home):
    seed_footprint(home)
    (home / "fakebin/claude").unlink()
    plan = un.build_plan(make_ctx(home))
    assert plan.mcp == []
    assert any("`claude` not found" in l for l in plan.report)


def test_plugin_detected_from_files_without_running_claude(home):
    seed_footprint(home)
    write(home / ".claude/plugins/installed_plugins.json",
          json.dumps({"version": 2, "plugins": {"voicemode@mbailey": [{}], "other@x": [{}]}}))
    runner = FakeRunner(home)
    plan = un.build_plan(make_ctx(home, runner=runner))
    assert any("claude plugin uninstall voicemode@mbailey" in l for l in plan.report)
    assert not any(a[0] == "claude" for a in runner.argvs())     # C6: read-only, no probe


def test_plugin_detected_from_enabled_plugins(home):
    write(home / ".claude/settings.json", json.dumps({"enabledPlugins": {"voicemode@voicemode": True}}))
    plan = un.build_plan(make_ctx(home))
    assert any("claude plugin uninstall voicemode@voicemode" in l for l in plan.report)


def test_hooks_path_from_ctx_home_not_settings_paths(home):
    seed_footprint(home)
    plan = un.build_plan(make_ctx(home))
    assert plan.hooks.path == home / ".claude/settings.json"
    assert plan.hooks.path != claude_mod.SETTINGS_PATHS["user"]


def test_hooks_removed_per_handler(home):
    seed_footprint(home)
    ctx = make_ctx(home)
    plan = un.build_plan(ctx)
    un.execute(plan, ctx, echo=lambda s: None)
    doc = json.loads((home / ".claude/settings.json").read_text())
    assert doc["theme"] == "dark"
    assert doc["hooks"] == {
        "Stop": [{"matcher": "", "hooks": [FOREIGN_HOOK]}],
        "PreToolUse": [{"matcher": "Bash", "hooks": [FOREIGN_HOOK]}],
    }


def test_symlinked_settings_inside_home_edited_at_target(home):
    target = write(home / "dotfiles/claude/settings.json", json.dumps(settings_doc()))
    target.chmod(0o640)
    link = home / ".claude/settings.json"
    link.parent.mkdir(parents=True)
    os.symlink(target, link)
    ctx = make_ctx(home)
    plan = un.build_plan(ctx)
    assert plan.hooks.target == Path(os.path.realpath(target))
    un.execute(plan, ctx, echo=lambda s: None)
    assert link.is_symlink()
    assert target.stat().st_mode & 0o777 == 0o640
    doc = json.loads(target.read_text())
    assert "PostToolUse" not in doc["hooks"] and doc["theme"] == "dark"


def test_symlinked_settings_outside_home_reported_untouched(home, tmp_path):
    target = write(tmp_path / "shared/settings.json", json.dumps(settings_doc()))
    before = target.read_bytes()
    link = home / ".claude/settings.json"
    link.parent.mkdir(parents=True)
    os.symlink(target, link)
    ctx = make_ctx(home)
    plan = un.build_plan(ctx)
    assert plan.hooks is None
    assert any("outside your home" in l for l in plan.report)
    un.execute(plan, ctx, echo=lambda s: None)
    assert target.read_bytes() == before


def test_project_hook_files_reported_not_edited(home):
    proj = home / "work/repo"
    f = write(proj / ".claude/settings.local.json", json.dumps(settings_doc()))
    before = f.read_bytes()
    ctx = make_ctx(home, cwd=proj)
    plan = un.build_plan(ctx)
    assert any("project file" in l for l in plan.report)
    un.execute(plan, ctx, echo=lambda s: None)
    assert f.read_bytes() == before


# ---------------------------------------------------------------------------
# Execute (temp HOME, fake runner)
# ---------------------------------------------------------------------------

READ_ONLY = (("launchctl", "print"), ("systemctl", "--user", "show"), ("uv", "tool", "dir"))


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_dry_run_changes_nothing(home, system):
    seed_footprint(home, system)
    runner = FakeRunner(home)
    ctx = make_ctx(home, system=system, runner=runner)
    before = snapshot(home)
    with patch.object(un, "make_context", lambda: ctx):
        result = CliRunner().invoke(un.uninstall, ["--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert snapshot(home) == before
    for argv in runner.argvs():
        assert any(tuple(argv[:len(k)]) == k for k in READ_ONLY), argv
    # the dry run prints every class of thing it would remove
    out = result.output
    for needle in ("would remove ~/.voicemode/services/voicemode",
                   "would back up ~/.voicemode/voicemode.env",
                   "claude mcp remove voicemode -s user",
                   "uv tool uninstall voice-mode",
                   "uv tool uninstall mlx-audio",
                   "VoiceMode hook handler"):
        assert needle in out, needle


def _expected_removed(plan, before: dict) -> set[str]:
    home = plan.home
    roots = [s.path for s in plan.removes] + [s for s, _ in plan.backups]
    roots += [u.path for u in plan.units] + [u.wants_link for u in plan.units if u.wants_link]
    roots = [rel(p, home) for p in roots]
    gone = {k for k in before if any(k == r or k.startswith(r + "/") for r in roots)}
    for d in plan.rmdirs:
        rd = rel(d, home)
        if rd in before and all(k in gone for k in before if k.startswith(rd + "/")):
            gone.add(rd)
    return gone


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
@pytest.mark.parametrize("flags", [{}, {"remove_models": True}, {"remove_all_data": True}])
def test_real_run_removes_exactly_the_plan(home, system, flags):
    seed_footprint(home, system)
    write(home / ".voicemode/soundfonts/real.sf2", "sf")
    os.symlink(home / ".voicemode/soundfonts/real.sf2", home / ".voicemode/soundfonts/current")
    runner = FakeRunner(home)
    ctx = make_ctx(home, system=system, runner=runner)
    before = snapshot(home)
    plan = un.build_plan(ctx, **flags)
    errors = un.execute(plan, ctx, echo=lambda s: None)
    assert errors == []
    assert un.remove_package(plan, ctx, errors, echo=lambda s: None) == 0
    after = snapshot(home)
    missing = set(before) - set(after)
    assert missing == _expected_removed(plan, before)
    # everything else is byte-identical, except the edited settings file
    for k, v in after.items():
        if k in before and k != ".claude/settings.json":
            assert before[k] == v, k
    for survivor in (".voicemode/voices/clone.wav", ".voicemode/voices.json",
                     ".voicemode/my-notes.txt", "kokoro-fastapi/main.py", ".claude.json"):
        assert survivor in after, survivor
    if system == "Darwin":
        assert "Library/LaunchAgents/com.voicemode.app.plist" in after
    new = set(after) - set(before)
    if flags.get("remove_all_data"):
        assert new == set()
    else:
        assert new == {".voicemode/voicemode.env.uninstalled"}
    assert runner.argvs()[-1] == ["uv", "tool", "uninstall", "voice-mode"]


def test_ordering_units_before_files_package_last(home, monkeypatch):
    seed_footprint(home)
    timeline: list = []
    plists = home / "Library/LaunchAgents"

    def loaded(argv):
        label = argv[2].split("/")[-1]
        return launchd_loaded(plists / f"{label}.plist") if argv[2].startswith("gui") else (113, "")
    runner = FakeRunner(home, {("launchctl", "print"): loaded}, timeline=timeline)
    real_remove = un._safe_remove

    def recording_remove(path, plan):
        timeline.append(("rm", str(path)))
        return real_remove(path, plan)
    monkeypatch.setattr(un, "_safe_remove", recording_remove)
    ctx = make_ctx(home, runner=runner)
    plan = un.build_plan(ctx)
    timeline.clear()
    errors = un.execute(plan, ctx, echo=lambda s: None)
    un.remove_package(plan, ctx, errors, echo=lambda s: None)
    last_bootout = max(i for i, e in enumerate(timeline)
                       if e[0] == "run" and e[1][:2] == ("launchctl", "bootout"))
    first_vm_rm = min(i for i, e in enumerate(timeline)
                      if e[0] == "rm" and "/.voicemode/" in e[1])
    assert last_bootout < first_vm_rm
    runs = [e for e in timeline if e[0] == "run"]
    assert runs[-1][1] == ("uv", "tool", "uninstall", "voice-mode")
    # hooks/MCP happen before any file in ~/.voicemode goes
    first_mcp = min(i for i, e in enumerate(timeline) if e[0] == "run" and e[1][:2] == ("claude", "mcp"))
    assert first_mcp < first_vm_rm


def test_error_keeps_package_and_rerun_finishes(home):
    seed_footprint(home)
    fail = {"on": True}

    def mcp(argv):
        return (1, "") if fail["on"] else (0, "")
    runner = FakeRunner(home, {("claude", "mcp", "remove"): mcp})
    ctx = make_ctx(home, runner=runner)
    with patch.object(un, "make_context", lambda: ctx):
        r1 = CliRunner().invoke(un.uninstall, ["--yes"])
    assert r1.exit_code == 1, r1.output
    assert "uv tool uninstall voice-mode" in r1.output
    assert ["uv", "tool", "uninstall", "voice-mode"] not in runner.argvs()
    fail["on"] = False
    with patch.object(un, "make_context", lambda: ctx):
        r2 = CliRunner().invoke(un.uninstall, ["--yes"])
    assert r2.exit_code == 0, r2.output
    assert runner.argvs()[-1] == ["uv", "tool", "uninstall", "voice-mode"]


def test_config_backup_never_clobbers(home):
    vm = home / ".voicemode"
    write(vm / "voicemode.env", "NEW=1\n")
    old = write(vm / "voicemode.env.uninstalled", "OPENAI_API_KEY=the-real-one\n")
    before = old.read_bytes()
    ctx = make_ctx(home)
    plan = un.build_plan(ctx)
    (src, dst), = plan.backups
    assert dst.name.startswith("voicemode.env.uninstalled.")
    un.execute(plan, ctx, echo=lambda s: None)
    assert old.read_bytes() == before
    assert dst.read_text() == "NEW=1\n"


def test_symlinks_unlinked_targets_untouched(home, tmp_path):
    vm = home / ".voicemode"
    target_sf = write(tmp_path / "sf-store/real.sf2", "sf")
    (vm / "soundfonts").mkdir(parents=True)
    os.symlink(target_sf, vm / "soundfonts/current")
    outside = write(tmp_path / "scratch-whisper/keep.bin", "keep")
    (vm / "services").mkdir(parents=True)
    os.symlink(outside.parent, vm / "services/whisper")
    ctx = make_ctx(home)
    plan = un.build_plan(ctx, remove_all_data=True)
    un.execute(plan, ctx, echo=lambda s: None)
    assert not os.path.lexists(vm / "services/whisper")
    assert outside.read_text() == "keep"
    assert target_sf.read_text() == "sf"


def test_symlinked_dir_inside_root_pointing_out_is_refused(home, tmp_path):
    """C5: `services` -> a scratch dir: services/whisper resolves outside the root."""
    vm = home / ".voicemode"
    vm.mkdir()
    scratch = tmp_path / "scratch"
    write(scratch / "whisper/model.bin", "keep")
    write(scratch / "voicemode/start.sh", "keep")
    os.symlink(scratch, vm / "services")
    before = snapshot(scratch)
    ctx = make_ctx(home)
    plan = un.build_plan(ctx, remove_all_data=True)
    assert un._safe_remove(vm / "services/whisper", plan) is not None
    # the plan never descends through the link: `services` itself is an unknown, kept
    assert vm / "services" in {p for p, _ in plan.kept}
    assert not any(str(s.path).startswith(str(vm / "services")) for s in plan.removes)
    errors = un.execute(plan, ctx, echo=lambda s: None)
    assert errors == []
    assert snapshot(scratch) == before


def test_safe_remove_refuses_hand_built_step(home, tmp_path):
    seed_footprint(home)
    plan = un.build_plan(make_ctx(home))
    victim = write(tmp_path / "victim.txt", "keep")
    assert un._safe_remove(victim, plan) is not None
    assert victim.exists()
    assert un._safe_remove(home / ".voicemode", plan) is not None       # never the root
    assert un._safe_remove(home / "kokoro-fastapi", plan) is not None
    assert (home / "kokoro-fastapi").exists()


def test_voices_dir_inside_a_removed_entry_is_protected(home):
    vm = home / ".voicemode"
    write(vm / "audio/voices/clone.wav")
    ctx = make_ctx(home, env={"VOICEMODE_VOICES_DIR": str(vm / "audio/voices")})
    plan = un.build_plan(ctx, remove_all_data=True)
    assert vm / "audio" not in {s.path for s in plan.removes}
    un.execute(plan, ctx, echo=lambda s: None)
    assert (vm / "audio/voices/clone.wav").exists()


# --- completion files (RF6, Q9, V4, C7) --------------------------------------

def test_completion_files_removed_when_bash_unsourced(home):
    seed_footprint(home)
    ctx = make_ctx(home)
    plan = un.build_plan(ctx)
    un.execute(plan, ctx, echo=lambda s: None)
    assert not (home / ".zfunc/_voicemode").exists()
    assert not (home / ".config/fish/completions/voicemode.fish").exists()
    assert not (home / ".bash_completion.d/voicemode").exists()
    assert (home / ".zfunc").is_dir()                  # directories never removed


@pytest.mark.parametrize("startup", [".bash_completion", ".bashrc", ".bashrc.d/50-voicemode.sh"])
def test_bash_completion_kept_when_sourced(home, startup):
    seed_footprint(home)
    write(home / startup, '. "$HOME/.bash_completion.d/voicemode"\n')
    ctx = make_ctx(home)
    plan = un.build_plan(ctx)
    assert home / ".bash_completion.d/voicemode" not in {s.path for s in plan.removes}
    assert any(startup in l and "sources it" in l for l in plan.report)
    un.execute(plan, ctx, echo=lambda s: None)
    assert (home / ".bash_completion.d/voicemode").exists()
    assert not (home / ".zfunc/_voicemode").exists()


# --- reports ----------------------------------------------------------------

def test_reports_credentials_custom_dirs_and_home_root(home, tmp_path):
    seed_footprint(home)
    write(home / "voicemode_debug.log")
    plan = un.build_plan(make_ctx(home, env={"VOICEMODE_MOUTH_DIR": str(tmp_path / "mouth")}))
    text = "\n".join(plan.report)
    assert "voicemode connect auth logout" in text and "credentials" in text
    assert "VOICEMODE_MOUTH_DIR" in text
    assert "voicemode_debug.log" in text
    plan2 = un.build_plan(make_ctx(home, env={"VOICEMODE_CREDENTIAL_STORE": "keyring"}))
    assert any("keychain" in l for l in plan2.report)
    plan3 = un.build_plan(make_ctx(home, env={"VOICEMODE_MOUTH_LOG_DIR": str(tmp_path / "ml")}))
    assert any("VOICEMODE_MOUTH_LOG_DIR" in l for l in plan3.report)


# ---------------------------------------------------------------------------
# CLI (CliRunner, through the make_context seam)
# ---------------------------------------------------------------------------

def _invoke(ctx, args, input=None):
    with patch.object(un, "make_context", lambda: ctx):
        return CliRunner().invoke(un.uninstall, args, input=input)


def test_cli_no_tty_without_yes_refuses(home):
    seed_footprint(home)
    ctx = make_ctx(home, interactive=False)
    before = snapshot(home)
    r = _invoke(ctx, [])
    assert r.exit_code == 2
    assert "VoiceMode uninstall: the plan." in r.output      # the plan is still printed
    assert "re-run with --yes" in r.output.lower()
    assert snapshot(home) == before


def test_cli_prompt_declined(home):
    seed_footprint(home)
    ctx = make_ctx(home, interactive=True)
    before = snapshot(home)
    r = _invoke(ctx, [], input="n\n")
    assert r.exit_code == 1, r.output
    assert "Remove the items above?" in r.output and "Nothing removed." in r.output
    assert snapshot(home) == before


def test_cli_prompt_accepted(home):
    seed_footprint(home)
    ctx = make_ctx(home, interactive=True)
    r = _invoke(ctx, [], input="y\n")
    assert r.exit_code == 0, r.output
    assert not (home / ".voicemode/bin").exists()


def test_cli_yes_proceeds(home):
    seed_footprint(home)
    runner = FakeRunner(home)
    ctx = make_ctx(home, runner=runner)
    r = _invoke(ctx, ["--yes"])
    assert r.exit_code == 0, r.output
    assert "Done." in r.output
    assert runner.argvs()[-1] == ["uv", "tool", "uninstall", "voice-mode"]


@pytest.mark.parametrize("kw", [{"uid": 0}, {"system": "Windows"}])
def test_cli_refusals(home, kw):
    seed_footprint(home)
    runner = FakeRunner(home)
    ctx = make_ctx(home, runner=runner, **kw)
    before = snapshot(home)
    r = _invoke(ctx, ["--yes"])
    assert r.exit_code == 2
    assert runner.calls == []
    assert snapshot(home) == before


def test_cli_home_mismatch_or_missing_refuses(home, tmp_path):
    seed_footprint(home)
    other = tmp_path / "other"
    other.mkdir()
    ctx = make_ctx(home, env={"HOME": str(other)})
    assert _invoke(ctx, ["--yes"]).exit_code == 2
    ctx2 = make_ctx(home)
    env2 = dict(ctx2.env)
    del env2["HOME"]
    ctx2 = un.Context(**{**ctx2.__dict__, "env": env2})
    assert _invoke(ctx2, ["--yes"]).exit_code == 2
    assert (home / ".voicemode/bin").exists()


def test_cli_help_names_flags_and_clones_rule():
    r = CliRunner().invoke(un.uninstall, ["--help"])
    assert r.exit_code == 0
    for flag in ("--dry-run", "--yes", "--remove-models", "--remove-all-data"):
        assert flag in r.output
    assert "never removed" in r.output and "Voice clones" in r.output


def test_registered_on_main_cli():
    from voice_mode.cli import voice_mode_main_cli
    assert voice_mode_main_cli.commands["uninstall"] is un.uninstall


def test_make_context_reads_tty(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    ctx = un.make_context()
    assert ctx.interactive is True and ctx.env is not os.environ


# ---------------------------------------------------------------------------
# The stale whisper-uninstall pointer (README criterion, design RF8/V5)
# ---------------------------------------------------------------------------

def test_whisper_uninstall_alias_points_at_real_commands():
    from voice_mode.cli import voice_mode_main_cli
    whisper = voice_mode_main_cli.commands["whisper"]
    alias = whisper.commands["uninstall"]
    # both commands it names really exist
    assert "uninstall" in whisper.commands["service"].commands
    assert "uninstall" in voice_mode_main_cli.commands
    assert "uninstall" not in voice_mode_main_cli.commands["service"].commands \
        if hasattr(voice_mode_main_cli.commands["service"], "commands") else True
    r = CliRunner().invoke(voice_mode_main_cli, ["whisper", "uninstall", "--help"])
    assert r.exit_code == 0
    out = " ".join(r.output.split())       # Click rewraps the docstring
    assert "voicemode whisper service uninstall" in out
    assert "voicemode uninstall" in out
    assert "service uninstall whisper" not in out
    assert "service uninstall whisper" not in (alias.help or "")


def test_whisper_uninstall_alias_warning_text():
    from voice_mode.cli import voice_mode_main_cli
    calls = []

    async def fake(**kwargs):          # a plain coroutine: no auto-created `.fn`
        calls.append(kwargs)
        return {"success": True}
    with patch("voice_mode.tools.whisper.uninstall.whisper_uninstall", fake):
        r = CliRunner().invoke(voice_mode_main_cli, ["whisper", "uninstall", "--yes"])
    assert r.exit_code == 0, r.output
    assert calls == [{"remove_models": False, "remove_all_data": False}]
    assert "voicemode whisper service uninstall" in r.output
    assert "to remove all of VoiceMode, use 'voicemode uninstall'" in r.output
    assert "service uninstall whisper" not in r.output


# ---------------------------------------------------------------------------
# Docs (do-002): docs/reference/uninstall.md tracks the code
# ---------------------------------------------------------------------------

DOC = Path(__file__).resolve().parent.parent / "docs" / "reference" / "uninstall.md"


def test_windows_refusal_points_at_the_docs_windows_section(home):
    ctx = make_ctx(home, system="Windows")
    r = _invoke(ctx, ["--dry-run"])
    assert r.exit_code == 2
    assert "docs/reference/uninstall.md#windows" in " ".join(r.output.split())
    # the anchor exists: mkdocs and GitHub both slug "## Windows" to #windows
    assert "\n## Windows\n" in DOC.read_text()


def test_docs_name_every_footprint_item_the_code_knows():
    """Every name the plan can act on or report is on the page.

    A name added to the code without the docs fails here, so the footprint
    list cannot silently drift from what the dry run prints.
    """
    doc = DOC.read_text()
    names = set(ENTRY.rstrip("/") for ENTRY in un.ENTRIES)
    names |= {f"com.voicemode.{s}.plist" for s in
              ("whisper", "kokoro", "serve", "mlx-audio")}
    names |= {f"{label}.plist" for label in un.MACOS_LEGACY_LABELS}
    names |= set(un.MACOS_GENERIC_PLISTS) | set(un.LINUX_GENERIC_UNITS)
    names |= {f"voicemode-{s}.service" for s in ("whisper", "kokoro", "serve")}
    names |= {"kokoro-fastapi-*.service", "default.target.wants"}
    names |= set(un.MCP_NAMES)
    names |= {un.COMPLETION_ZSH, un.COMPLETION_FISH, un.COMPLETION_BASH}
    names |= set(un.BASH_STARTUP_FILES) | set(un.BASH_STARTUP_DIRS)
    names |= set(un.CUSTOM_LOCATION_VARS)
    names |= set(un.HOME_ROOT_FILES) | set(un.HOME_ROOT_GLOBS)
    names |= {"voicemode.env.uninstalled", "uv tool uninstall voice-mode",
              "uv tool uninstall mlx-audio", "uv cache clean voice-mode",
              "voicemode connect auth logout", "claude plugin uninstall voicemode@voicemode",
              "-s local", "--dry-run", "--yes", "--remove-models", "--remove-all-data"}
    for name in sorted(names):
        bare = name.lstrip(".")         # ".voicemode.env" is written `.voicemode.env`
        assert name in doc or bare in doc, f"{name!r} is not in {DOC.name}"

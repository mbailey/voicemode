"""simpleaudio stays out of VoiceMode (#541, VM-2438, VM-2536).

simpleaudio 1.0.4 has no wheel for Apple Silicon or for any Python VoiceMode
supports on Windows, so as a dependency it forced a C compiler onto every Mac
and Windows install. Nothing imported it. These tests keep it from coming back.
"""

import ast
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def project_dependencies(pyproject_text: str) -> list[str]:
    """The names in pyproject's [project] dependencies list."""
    block = re.search(
        r"^\[project\].*?^dependencies\s*=\s*\[(.*?)^\]", pyproject_text, re.S | re.M
    )
    assert block, "no [project] dependencies list in pyproject.toml"
    specs = re.findall(r'^\s*"([^"]+)"', block.group(1), re.M)
    return [re.split(r"[\s<>=!~;\[]", spec, maxsplit=1)[0].lower() for spec in specs]


def locked_packages(lock_text: str) -> set[str]:
    """Every package name uv.lock resolves."""
    return set(re.findall(r'^\[\[package\]\]\nname = "([^"]+)"', lock_text, re.M))


def simpleaudio_imports(source_root: Path) -> list[str]:
    """file:line for every import of simpleaudio under source_root."""
    hits = []
    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n == "simpleaudio" or n.startswith("simpleaudio.") for n in names):
                hits.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return hits


def test_simpleaudio_is_not_a_dependency():
    deps = project_dependencies((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "pydub" in deps, "parser sanity: pydub should be found"
    assert "simpleaudio" not in deps


def test_simpleaudio_is_not_in_the_lock():
    packages = locked_packages((ROOT / "uv.lock").read_text(encoding="utf-8"))
    assert "pydub" in packages, "parser sanity: pydub should be found"
    assert "simpleaudio" not in packages


def test_nothing_imports_simpleaudio():
    assert simpleaudio_imports(ROOT / "voice_mode") == []


def test_alsa_headers_are_optional_on_linux():
    """Core needed them only to compile simpleaudio (whisper's build is separate)."""
    deps = yaml.safe_load((ROOT / "voice_mode" / "dependencies.yaml").read_text())
    core = deps["voicemode"]["core"]
    required = {
        pkg["name"]: pkg.get("required")
        for distro in ("debian", "fedora")
        for pkg in core[distro]["packages"]
    }
    assert required["libasound2-dev"] is False
    assert required["alsa-lib-devel"] is False

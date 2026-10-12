"""Repository integration check for bundled Agent numbering and registration."""

from pathlib import Path
import shutil
import subprocess

import pytest

from agentbench.harness.registry import load_registry, tomllib


def test_bundled_agent_directories_match_registry_and_have_contiguous_numbers():
    root = Path(__file__).resolve().parents[1]
    registry_path = root / "resources" / "registry.toml"
    units_root = root / "resources" / "agents"
    if not registry_path.is_file() or not units_root.is_dir():
        pytest.skip("Requires a repository checkout containing bundled Agent units")

    with registry_path.open("rb") as stream:
        entries = tomllib.load(stream)["agents"]

    registered_paths = [root / entry["path"] for entry in entries]
    units = {path for path in units_root.iterdir() if path.is_dir()}
    assert len(set(registered_paths)) == len(entries), "Duplicate registered Agent paths"
    assert set(registered_paths) == units, "Bundled directories and registry must agree"

    numbers = []
    for unit in units:
        prefix, separator, name = unit.name.partition("-")
        assert separator and prefix.isdecimal() and name, unit.name
        numbers.append(int(prefix))
        assert prefix == f"{int(prefix):02d}", unit.name
    assert sorted(numbers) == list(range(1, len(units) + 1)), (
        "Agent numbers must be unique and contiguous from 01"
    )

    registry = load_registry(registry_path)
    for entry in entries:
        assert registry.find(entry["agent_id"], enabled_only=False).path == (
            root / entry["path"]
        ).resolve()


def test_agent_source_is_untracked_and_ignored_for_every_registered_unit():
    root = Path(__file__).resolve().parents[1]
    if not shutil.which("git") or not (root / ".git").exists():
        pytest.skip("Requires a Git checkout")
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z", "resources/agents"],
        text=True, encoding="utf-8",
    ).split("\0")
    assert not [path for path in tracked if len(Path(path).parts) >= 4
                and Path(path).parts[3] == "agent"], "Agent source must not be committed"
    with (root / "resources/registry.toml").open("rb") as stream:
        entries = tomllib.load(stream)["agents"]
    paths = [entry["path"] + "/agent/source.txt" for entry in entries]
    ignored = subprocess.check_output(
        ["git", "-C", str(root), "check-ignore", "--no-index", "--stdin", "-z"],
        input=("\0".join(paths) + "\0").encode("utf-8"),
    ).decode("utf-8").rstrip("\0").split("\0")
    assert ignored == paths, "Every registered Agent source must be ignored"

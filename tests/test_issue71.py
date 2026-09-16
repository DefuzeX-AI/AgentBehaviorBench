"""Issue #71: `agent add` names, URLs, discovery, submodules and symlinks."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentbench.cli.main import cli
from agentbench.onboarding.discovery import discover_files
from agentbench.onboarding.source import AgentDownloadError, download_agent

FIRST = "https://github.com/example/my-agent"
SECOND = "https://github.com/other-owner/my-agent"


def write(root: Path, name: str, content: str = "fixture\n") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(directory), "-c", "user.name=ABB Test", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=", "-c", "protocol.file.allow=always", *arguments],
        check=True, capture_output=True, text=True).stdout


def upstream(root: Path, name: str, files: dict[str, str]) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    for relative, content in files.items():
        write(directory, relative, content)
    git(directory, "init", "-q")
    git(directory, "add", ".")
    git(directory, "commit", "-qm", "fixture")
    return directory


@pytest.fixture
def github(tmp_path, monkeypatch):
    """Serve the given GitHub URLs from local repositories through url.insteadOf."""
    def serve(mapping: dict[str, Path]):
        monkeypatch.setenv("GIT_CONFIG_COUNT", str(len(mapping)))
        for index, (url, directory) in enumerate(mapping.items()):
            monkeypatch.setenv(f"GIT_CONFIG_KEY_{index}", f"url.{directory.as_uri()}.insteadOf")
            monkeypatch.setenv(f"GIT_CONFIG_VALUE_{index}", url)
    return serve


# D1 -------------------------------------------------------------------------

def test_same_named_repositories_of_different_owners_both_download(tmp_path, github):
    first = upstream(tmp_path / "up", "first", {"README.md": "one"})
    second = upstream(tmp_path / "up", "second", {"README.md": "two"})
    github({FIRST: first, SECOND: second})
    root = tmp_path / "agents"

    assert download_agent(FIRST, root).directory.name == "01-my-agent"
    added = download_agent(SECOND, root)

    assert added.directory.name == "02-other-owner-my-agent"
    manifest = json.loads((added.directory / "source-manifest.json").read_text())
    assert manifest["repository"] == SECOND
    assert (added.directory / "agent" / "README.md").read_text() == "two"


def test_the_same_repository_and_unrecorded_units_are_still_duplicates(tmp_path, github):
    github({FIRST: upstream(tmp_path / "up", "first", {"README.md": "one"})})
    root = tmp_path / "agents"
    download_agent(FIRST, root)
    with pytest.raises(AgentDownloadError, match="Agent directory already exists: .*01-my-agent"):
        download_agent(FIRST + ".git", root)

    unrecorded = tmp_path / "manual"
    (unrecorded / "04-my-agent").mkdir(parents=True)
    with pytest.raises(AgentDownloadError, match="already exists: .*04-my-agent"):
        download_agent(SECOND, unrecorded)


# D7 -------------------------------------------------------------------------

def test_github_tab_query_is_accepted_and_other_queries_name_the_problem(tmp_path, github):
    github({FIRST: upstream(tmp_path / "up", "first", {"README.md": "one"})})
    added = download_agent(FIRST + "?tab=readme-ov-file", tmp_path / "agents")
    assert json.loads((added.directory / "source-manifest.json").read_text())["repository"] == FIRST
    for url in (FIRST + "?token=secret", FIRST + "#readme", FIRST + "?tab=a&token=b"):
        with pytest.raises(AgentDownloadError, match="Remove the query string or fragment"):
            download_agent(url, tmp_path / "refused")


def test_owner_error_names_the_owner_not_a_branch_url(tmp_path):
    with pytest.raises(AgentDownloadError, match="Invalid GitHub owner 'some.owner'"):
        download_agent("https://github.com/some.owner/repo", tmp_path / "agents")
    with pytest.raises(AgentDownloadError, match="not a GitHub file or branch URL"):
        download_agent(FIRST + "/tree/main", tmp_path / "agents")


# D2 -------------------------------------------------------------------------

def test_discovery_lists_the_build_inputs_it_used_to_miss(tmp_path):
    expected = ["front/package.json", "Makefile", "README_CN.md", "README-ja_JP.md", "tools/go.mod",
                ".env-example", "server/.env example", "front/DockerfileDev", "Dockerfile_cpu_base",
                ".nvmrc", ".tool-versions", "docker/compose.mongo.yaml", "engine/Cargo.toml"]
    for name in [*expected, ".env", "notes.txt"]:
        write(tmp_path, name)
    found = discover_files(tmp_path)
    assert set(expected) <= set(found)
    assert ".env" not in found and "notes.txt" not in found


# D3, D4 ---------------------------------------------------------------------

def test_submodules_that_cannot_be_fetched_are_recorded_and_reported(tmp_path, github, capsys):
    library = upstream(tmp_path / "up", "library", {"lib.py": "VALUE = 1\n"})
    main = upstream(tmp_path / "up", "main", {"README.md": "main"})
    # A local-path submodule stands in for any non-HTTPS URL, which agent add refuses to fetch.
    git(main, "submodule", "add", "-q", library.as_uri(), "vendor/library")
    git(main, "commit", "-qm", "add submodule")
    github({FIRST: main})
    root = tmp_path / "agents"

    assert cli(["agent", "add", FIRST, "--agents-dir", str(root)]) == 0

    unit = root / "01-my-agent"
    manifest = json.loads((unit / "source-manifest.json").read_text())
    assert manifest["submodules"] == [
        {"path": "vendor/library", "revision": git(library, "rev-parse", "HEAD").strip(), "initialized": False}]
    assert list((unit / "agent" / "vendor" / "library").iterdir()) == []
    assert "Warning: Submodules left empty, so the vendored source is incomplete: vendor/library" \
        in capsys.readouterr().err


def test_symlinks_are_reported_at_download_time(tmp_path, github, capsys):
    main = tmp_path / "up" / "main"
    write(main, "README.md", "main")
    write(main, "skills/real/SKILL.md", "skill")
    (main / ".claude").mkdir()
    (main / ".claude" / "skills").symlink_to("../skills")
    git(main, "init", "-q")
    git(main, "add", ".")
    git(main, "commit", "-qm", "fixture")
    github({FIRST: main})

    added = download_agent(FIRST, tmp_path / "agents")

    assert added.warnings == ("1 symlink(s) kept; the Docker build context refuses symlinks, "
                              "so replace or remove them before building: .claude/skills",)
    assert "submodules" not in json.loads((added.directory / "source-manifest.json").read_text())


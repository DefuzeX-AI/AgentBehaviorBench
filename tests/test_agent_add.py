"""Source onboarding through the real CLI and a local Git transport fixture."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agentbench.cli.main import cli
from agentbench.onboarding.discovery import discover_files
from agentbench.onboarding.resume import download_or_reuse
from agentbench.onboarding.source import AgentDownloadError, download_agent


URL = "https://github.com/example/my-agent"


def test_cli_explains_reversed_agent_add_command(capsys):
    with pytest.raises(SystemExit) as raised:
        cli(["add", "agent", r"C:\agent-source"])

    assert raised.value.code == 2
    error = capsys.readouterr().err
    assert "'add' is not a top-level command" in error
    assert "Correct command: agentbench agent add SOURCE" in error
    assert "agentbench agent add --help" in error


def test_cli_explains_that_local_directories_do_not_need_d_flag(capsys):
    with pytest.raises(SystemExit) as raised:
        cli(["agent", "add", r"C:\agent-source", "-d"])

    assert raised.value.code == 2
    error = capsys.readouterr().err
    assert "-d is not required" in error
    assert "agentbench agent add SOURCE" in error
    assert "--agents-dir DIRECTORY" in error


def test_agent_add_help_explains_local_sources_and_destination(capsys):
    with pytest.raises(SystemExit) as raised:
        cli(["agent", "add", "--help"])

    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    assert "Local directories are detected automatically; do not use -d" in help_text
    assert "agentbench agent add C:\\path\\to\\agent" in help_text
    assert "--agents-dir DIRECTORY" in help_text


def write(root: Path, name: str, content: str = "fixture\n") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def repository(tmp_path, monkeypatch):
    """Use actual git clone/rev-parse without network or a production checkout."""
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    write(upstream, "README.md")
    write(upstream, "pyproject.toml", '[project]\nname = "fixture"\nversion = "0.1"\n')
    write(upstream, "langgraph.json", json.dumps({"graphs": {"agent": "./src/graph.py:graph"}}))
    write(upstream, "src/graph.py", 'raise AssertionError("onboarding must not import this")\n')
    write(upstream, "notes.txt")
    for command in (["init", "-q"], ["add", "."], ["commit", "-qm", "Agent fixture"]):
        subprocess.run(
            ["git", "-C", str(upstream), "-c", "user.name=ABB Test",
             "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
             "-c", "core.hooksPath=", *command],
            check=True, capture_output=True, text=True,
        )
    revision = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True,
    ).strip()
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{upstream.as_uri()}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", URL)
    return upstream, revision


def test_cli_downloads_numbered_source_and_prints_json_array(repository, tmp_path, capsys):
    root = tmp_path / "resources/agents"
    existing = write(root, "09-existing/agent/keep.txt", "keep unchanged")
    registry = write(root.parent, "registry.toml", 'schema_version = "defuzex-bench.registry.v1"\n')
    registry_before = registry.read_bytes()

    assert cli(["agent", "add", URL + ".git", "--agents-dir", str(root)]) == 0

    output = capsys.readouterr()
    assert json.loads(output.out) == ["README.md", "langgraph.json", "pyproject.toml", "src/graph.py"]
    unit = root / "10-my-agent"
    assert str(unit) in output.err
    assert (unit / "agent/notes.txt").read_text() == "fixture\n"
    assert not (unit / "agent/.git").exists()
    source = json.loads((unit / "source-manifest.json").read_text())
    assert source["repository"] == URL
    assert source["revision"] == repository[1]
    assert existing.read_text() == "keep unchanged"
    assert registry.read_bytes() == registry_before
    assert not (unit / "agent.toml").exists()
    assert not list(root.glob(".agent-add-*"))


def test_default_destination_follows_cli_registry_location(repository, tmp_path, monkeypatch, capsys):
    from agentbench.cli.features import agent as feature

    registry = tmp_path / "project/resources/registry.toml"
    monkeypatch.setattr(feature, "DEFAULT_REGISTRY_PATH", registry)
    monkeypatch.chdir(tmp_path)
    assert cli(["agent", "add", URL]) == 0
    assert (registry.parent / "agents/01-my-agent/agent/langgraph.json").is_file()
    assert json.loads(capsys.readouterr().out)


def test_cli_copies_absolute_local_directory_into_numbered_unit(tmp_path, capsys):
    local = tmp_path / "Local Agent"
    write(local, "README.md", "local source\n")
    write(local, "langgraph.json", json.dumps({"graphs": {"agent": "./graph.py:graph"}}))
    write(local, "graph.py", "graph = object()\n")
    write(local, "notes.txt", "copied too\n")
    write(local, ".git/config", "must not be copied\n")
    root = tmp_path / "project/resources/agents"

    assert cli(["agent", "add", str(local.resolve()), "--agents-dir", str(root)]) == 0

    output = capsys.readouterr()
    assert json.loads(output.out) == ["README.md", "graph.py", "langgraph.json"]
    unit = root / "01-local-agent"
    assert (unit / "agent/notes.txt").read_text() == "copied too\n"
    assert not (unit / "agent/.git").exists()
    metadata = json.loads((unit / "source-manifest.json").read_text())
    assert metadata["repository"] == str(local.resolve())
    assert metadata["source_type"] == "local-directory"
    assert metadata["revision"].startswith("sha256:")
    assert len(metadata["revision"].removeprefix("sha256:")) == 64
    assert "Local source copied" in output.err
    assert not list(root.glob(".agent-add-*"))


def test_local_source_reuse_matches_its_canonical_absolute_path(tmp_path):
    local = tmp_path / "local-agent"
    write(local, "README.md", "original\n")
    root = tmp_path / "agents"
    first = download_agent(str(local.resolve()), root)
    write(local, "README.md", "changed after import\n")

    reused = download_or_reuse(str(local.resolve()), root)

    assert reused.directory == first.directory
    assert (reused.directory / "agent/README.md").read_text() == "original\n"
    assert reused.revision == first.revision


def test_local_source_reuse_does_not_require_the_original_after_import(tmp_path):
    local = tmp_path / "local-agent"
    write(local, "README.md")
    root = tmp_path / "agents"
    first = download_agent(str(local.resolve()), root)
    original_identifier = first.repository
    shutil.rmtree(local)

    reused = download_or_reuse(original_identifier, root)

    assert reused.directory == first.directory


def test_cli_local_source_enters_the_existing_build_workflow(tmp_path, monkeypatch, capsys):
    from agentbench.onboarding import workflow

    local = tmp_path / "local-agent"
    write(local, "README.md")
    root = tmp_path / "agents"
    observed = []

    def configure(source, args, *, output_fn):
        observed.append((source, args.build, args.certify))
        output_fn("build workflow reached")
        return 17

    monkeypatch.setattr(workflow, "configure_download", configure)

    assert cli(["agent", "add", str(local.resolve()), "--agents-dir", str(root), "-b"]) == 17
    source, build, certify = observed[0]
    assert source.directory == root / "01-local-agent"
    assert source.source_type == "local-directory"
    assert build is True and certify is False
    assert "build workflow reached" in capsys.readouterr().err


def test_duplicate_local_add_does_not_overwrite_imported_source(tmp_path, capsys):
    local = tmp_path / "local-agent"
    write(local, "README.md", "original\n")
    root = tmp_path / "agents"
    result = download_agent(str(local.resolve()), root)
    write(result.directory, "agent/README.md", "integration edit\n")

    assert cli(["agent", "add", str(local.resolve()), "--agents-dir", str(root)]) == 2

    assert "already exists" in capsys.readouterr().err
    assert (result.directory / "agent/README.md").read_text() == "integration edit\n"


def test_same_named_local_directories_receive_distinct_unit_names(tmp_path):
    first = tmp_path / "one/shared/local-agent"
    second = tmp_path / "two/shared/local-agent"
    third = tmp_path / "three/shared/local-agent"
    for index, path in enumerate((first, second, third), 1):
        write(path, "README.md", str(index))
    root = tmp_path / "agents"

    imported = [download_agent(str(path.resolve()), root) for path in (first, second, third)]

    assert imported[0].directory.name == "01-local-agent"
    assert imported[1].directory.name == "02-shared-local-agent"
    assert imported[2].directory.name.startswith("03-shared-local-agent-")
    assert len({item.directory.name for item in imported}) == 3


def test_local_source_must_be_an_absolute_directory(tmp_path, monkeypatch):
    local = tmp_path / "local-agent"
    local.mkdir()
    file_source = write(tmp_path, "agent.py")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(AgentDownloadError, match="absolute directory"):
        download_agent("local-agent", tmp_path / "agents")
    with pytest.raises(AgentDownloadError, match="not a directory"):
        download_agent(str(file_source.resolve()), tmp_path / "agents")
    with pytest.raises(AgentDownloadError, match="does not exist"):
        download_agent(str((tmp_path / "missing").resolve()), tmp_path / "agents")


def test_local_source_cannot_contain_agents_destination(tmp_path):
    local = tmp_path / "local-agent"
    local.mkdir()
    root = local / "resources/agents"

    with pytest.raises(AgentDownloadError, match="inside the local source"):
        download_agent(str(local.resolve()), root)

    assert not root.exists()


def test_interrupted_local_copy_cleans_staging(tmp_path, monkeypatch):
    local = tmp_path / "local-agent"
    write(local, "README.md")
    root = tmp_path / "agents"

    def fail_copy(_source, target, **_kwargs):
        write(Path(target), "partial.txt")
        raise OSError("copy interrupted")

    monkeypatch.setattr("agentbench.onboarding.source.shutil.copytree", fail_copy)

    with pytest.raises(OSError, match="copy interrupted"):
        download_agent(str(local.resolve()), root)

    assert list(root.iterdir()) == []


def test_duplicate_add_does_not_overwrite_download(repository, tmp_path, capsys):
    root = tmp_path / "agents"
    result = download_agent(URL, root)
    write(result.directory, "agent/README.md", "local changes")

    assert cli(["agent", "add", URL, "--agents-dir", str(root)]) == 2
    assert "already exists" in capsys.readouterr().err
    assert (result.directory / "agent/README.md").read_text() == "local changes"
    assert [path.name for path in root.iterdir()] == ["01-my-agent"]


def test_clone_failure_cleans_staging_and_preserves_existing_units(tmp_path, monkeypatch, capsys):
    root = tmp_path / "agents"
    kept = write(root, "05-kept/agent/README.md")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{(tmp_path / 'missing').as_uri()}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", URL)

    assert cli(["agent", "add", URL, "--agents-dir", str(root)]) == 2
    output = capsys.readouterr()
    assert "Git operation failed" in output.err
    assert output.out == ""
    assert kept.is_file()
    assert [path.name for path in root.iterdir()] == ["05-kept"]


@pytest.mark.parametrize("failure", [FileNotFoundError(), subprocess.TimeoutExpired("git", 1), KeyboardInterrupt()])
def test_interrupted_download_cleans_staging(tmp_path, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr("agentbench.onboarding.source.subprocess.run", fail)
    expected = KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else AgentDownloadError
    root = tmp_path / "agents"
    with pytest.raises(expected):
        download_agent(URL, root, timeout=1)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("url", [
    "git@github.com:example/my-agent.git", "https://example.org/my-agent",
    "https://github.com/example/my-agent/tree/main", "https://github.com/example",
    "https://secret@github.com/example/my-agent", URL + "?token=secret",
    "https://github.com/example/..", "--upload-pack=unexpected", "https://[invalid",
])
def test_invalid_source_never_creates_destination(tmp_path, url):
    root = tmp_path / "agents"
    with pytest.raises(AgentDownloadError):
        download_agent(url, root)
    assert not root.exists()


def test_scan_nested_configs_entrypoints_and_setup_files_without_executing(tmp_path):
    write(tmp_path, "README.zh-CN.md")
    write(tmp_path, "requirements-dev.txt")
    write(tmp_path, "requirements/base.txt")
    write(tmp_path, "Dockerfile.cpu")
    write(tmp_path, ".env.example")
    write(tmp_path, ".env", "never include a real secret file")
    write(tmp_path, "app/langgraph.json", json.dumps({"graphs": {
        "agent": {"path": "../src/graph.py:graph"},
        "again": "../src/graph.py:graph",
        "missing": "./missing.py:graph",
        "escape": "../../outside.py:graph",
    }}))
    write(tmp_path, "src/graph.py", 'raise AssertionError("do not import")\n')
    write(tmp_path, "examples/langgraph.json", "invalid JSON still needs to be listed")
    for directory in (".git", ".venv", "node_modules"):
        write(tmp_path, directory + "/README.md")
    assert discover_files(tmp_path) == (
        ".env.example", "Dockerfile.cpu", "README.zh-CN.md", "app/langgraph.json",
        "examples/langgraph.json", "requirements-dev.txt", "requirements/base.txt", "src/graph.py",
    )


def test_scan_does_not_follow_symlinks(tmp_path):
    outside = tmp_path / "outside"
    write(outside, "graph.py")
    root = tmp_path / "agent"
    write(root, "langgraph.json", json.dumps({"graphs": {"agent": "linked/graph.py:graph"}}))
    (root / "linked").symlink_to(outside, target_is_directory=True)
    (root / "README.md").symlink_to(outside / "graph.py")
    assert discover_files(root) == ("langgraph.json",)


def test_scan_empty_repository_is_an_empty_array(tmp_path):
    write(tmp_path, "unrelated.txt")
    assert discover_files(tmp_path) == ()

"""Preserve installation constraints without unbounded or unsafe source reads."""

from dataclasses import replace
import json

import pytest

from agentbench.onboarding.build_agent_env.openrouter_provider.context import collect_context
from agentbench.onboarding.build_agent_env.openrouter_provider.lock_context import read_lock_excerpt
from agentbench.onboarding.build_agent_env.openrouter_provider.settings import load_settings
from agentbench.onboarding.discovery import discover_files
from tests.agent_build_fixtures import source, write


def test_uv_python_constraint_reaches_model_context(source):
    write(source.directory, "agent/uv.lock", 'version = 1\nrequires-python = ">=3.13"\n')
    source = replace(source, files=discover_files(source.directory / "agent"))
    context = collect_context(source, load_settings(), {})
    lock = next(item for item in context["files"] if item["path"] == "uv.lock")
    assert 'requires-python = ">=3.13"' in lock["content"]
    assert lock["truncated"] is False


def test_large_lock_preserves_header_footer_with_explicit_omissions(source):
    write(source.directory, "agent/poetry.lock",
          '# HEADER\n' + 'package-data\n' * 2000 + '\n[metadata]\npython-versions = ">=3.13"\n')
    source = replace(source, files=("poetry.lock",))
    settings = replace(load_settings(), max_file_bytes=256, max_context_bytes=256)
    context = collect_context(source, settings, {})
    lock = context["files"][0]
    assert '# HEADER' in lock["content"]
    assert 'python-versions = ">=3.13"' in lock["content"]
    assert lock["truncated"] and "omitted" in lock["excerpt"]
    assert 'LOCK CONTENT OMITTED' in lock["content"]
    assert context["content_bytes"] <= 256


def test_hash_lock_is_discovered_and_redacted_but_symlink_is_excluded(source, tmp_path):
    secret = "lock-private-token-12345678"
    write(source.directory, "agent/dependencies.lock", f"# {secret}\nexample==1.0\n")
    outside = write(tmp_path, "private.lock", "HOST_ONLY_CONTENT")
    (source.directory / "agent/uv.lock").symlink_to(outside)
    found = discover_files(source.directory / "agent")
    assert "dependencies.lock" in found and "uv.lock" not in found
    source = replace(source, files=("dependencies.lock", "uv.lock"))
    context = collect_context(source, load_settings(), {"TOKEN": secret})
    assert secret not in json.dumps(context) and "HOST_ONLY_CONTENT" not in json.dumps(context)
    assert [item["path"] for item in context["files"]] == ["dependencies.lock"]


@pytest.mark.parametrize("budget", [1, 16, 57, 58, 59, 100, 257])
def test_lock_excerpt_handles_utf8_boundaries_and_small_budgets(tmp_path, budget):
    path = write(tmp_path, "uv.lock", "约束" * 1000)
    content, truncated = read_lock_excerpt(path, budget)
    assert truncated and len(content.encode()) <= budget


def test_lock_obeys_total_context_budget(source):
    for name in ("uv.lock", "poetry.lock"):
        write(source.directory, "agent/" + name, "data" * 1000)
    source = replace(source, files=("uv.lock", "poetry.lock"))
    context = collect_context(source, replace(load_settings(),
                              max_file_bytes=100, max_context_bytes=150), {})
    assert context["content_bytes"] <= 150
    assert sum(len(item["content"].encode()) for item in context["files"]) == context["content_bytes"]

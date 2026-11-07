"""Regression test suite for Issue #448 alibaba/open-code-review onboarding."""

import json
from pathlib import Path
import pytest
from agentbench.harness.registry import load_registry, tomllib
from kuma.repository.agent_profiles import parse_agent_profile

ROOT = Path(__file__).resolve().parents[1]
UNIT_DIR = ROOT / "resources" / "agents" / "122-open-code-review"


def test_registry_contract():
    registry_path = ROOT / "resources" / "registry.toml"
    with registry_path.open("rb") as f:
        data = tomllib.load(f)["agents"]
    entry = next((e for e in data if e["agent_id"] == "open-code-review"), None)
    assert entry is not None, "open-code-review must be in registry.toml"
    assert entry["enabled"] is False, "status='adapting' must have enabled=false"
    assert entry["status"] == "adapting"
    assert entry["framework"] == "acp"
    assert entry["path"] == "resources/agents/122-open-code-review"


def test_agent_toml_contract():
    agent_toml_path = UNIT_DIR / "agent.toml"
    assert agent_toml_path.is_file()
    with agent_toml_path.open("rb") as f:
        data = tomllib.load(f)
    assert data["schema_version"] == "defuzex-bench.agent.v2"
    assert data["agent_id"] == "open-code-review"
    assert data["framework"] == "acp"
    assert data["runtime"]["secret_env_keys"] == []
    assert data["adapter"]["type"] == "acp"
    assert data["adapter"]["transport"] == "stdio"


def test_network_rules_contract():
    rules_path = UNIT_DIR / "network" / "rules.toml"
    assert rules_path.is_file()
    with rules_path.open("rb") as f:
        data = tomllib.load(f)
    assert data["schema_version"] == "abb.network.v1"
    # Default model selection: no provider-specific routes.
    assert data.get("tool_routes", []) == []


def test_launcher_passes_acp_through():
    launch_text = (UNIT_DIR / "bootstrap" / "launch.py").read_text(encoding="utf-8")
    assert "os.execvpe" in launch_text
    assert "session/prompt" not in launch_text
    assert not (UNIT_DIR / "bootstrap" / "sitecustomize.py").exists()


def test_kuma_requirement_profile():
    req_path = UNIT_DIR / "requirement.md"
    assert req_path.is_file()
    text = req_path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "Profile must start with YAML front matter"
    assert len(text) < 4000, f"Profile exceeds 4000 chars: {len(text)}"
    profile = parse_agent_profile(req_path)
    assert profile.agent_description, "Profile must have agent_description"
    assert (
        getattr(profile.strategy_group, "id", profile.strategy_group)
        == "basic-safety-coding"
    )
    assert len(profile.sections) >= 3, "Must have 3 sections"


def test_source_manifest():
    manifest_path = UNIT_DIR / "source-manifest.json"
    assert manifest_path.is_file()
    with manifest_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["repository"] == "https://github.com/alibaba/open-code-review"
    assert data["revision"] == "375f64cd6f67a48a135da83cfcf59c52669a09cb"
    assert data["license"] == "Apache-2.0"


def test_token_redaction():
    launch_text = (UNIT_DIR / "bootstrap" / "launch.py").read_text(encoding="utf-8")
    assert "[REDACTED]" in launch_text


def test_no_source_tracked():
    agent_dir = UNIT_DIR / "agent"
    if agent_dir.is_dir():
        import subprocess

        res = subprocess.run(
            ["git", "status", "--porcelain", str(agent_dir)],
            capture_output=True,
            text=True,
        )
        assert res.stdout.strip() == "", "Agent source must not be tracked in git"

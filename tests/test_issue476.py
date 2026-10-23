"""Offline regression coverage for native ACP onboarding Issue #476."""
from pathlib import Path
import importlib.util
import json
import os
import tomllib
import pytest
ROOT = Path(os.environ.get("ABB_UNIT_TEST_ROOT", Path(__file__).resolve().parents[1]))
UNIT = ROOT / "resources/agents/78-easy-agent"

def launcher():
    spec = importlib.util.spec_from_file_location("launch_476", UNIT / "bootstrap/launch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def environment():
    return {"ABB_AGENT_MODEL_API_KEY": "synthetic-fixture-key", "ABB_AGENT_MODEL_BASE_URL": "https://fixture.example/v1", "ABB_AGENT_MODEL": "fixture-model"}

def test_unit_and_registry_contract():
    data = tomllib.loads((UNIT / "agent.toml").read_text())
    assert data["agent_id"] == "easy-agent" and data["framework"] == "acp"
    assert data["source"]["revision"] == "aec616a97114ce9683e4fbfcff3abbc55155fe50"
    assert data["adapter"]["permission_policy"] == "allow_once"
    assert data["evaluation"]["file_evidence"]["track_files"] is True
    registry = tomllib.loads((ROOT / "resources/registry.toml").read_text())
    entry = next(x for x in registry["agents"] if x["agent_id"] == "easy-agent")
    assert entry["status"] == "adapting" and entry["enabled"] is False

def test_profile_has_deployed_contract_and_no_gt_claim():
    text = (UNIT / "requirement.md").read_text()
    assert text.startswith("---\n") and "input_type: text" in text
    for heading in ["Production Use Scenario", "Behaviors to Test", "Known Limitations or Prohibited Behaviors"]:
        assert "## " + heading in text
    assert "empty writable workspace" in text

@pytest.mark.parametrize("missing", ["ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL"])
def test_missing_runtime_selection_fails_without_fallback(missing):
    env = environment(); del env[missing]
    with pytest.raises(ValueError, match=missing):
        launcher().prepare(env)

@pytest.mark.parametrize("url", ["http://fixture.example/v1", "https://u:p@fixture.example/v1", "https://fixture.example/v1?token=x", "https://fixture.example/v1#x"])
def test_invalid_endpoint_is_rejected(url):
    env = environment(); env["ABB_AGENT_MODEL_BASE_URL"] = url
    with pytest.raises(ValueError):
        launcher().prepare(env)

def test_selected_model_is_not_silently_replaced():
    env = environment(); command, child, settings = launcher().prepare(env)
    assert command and "synthetic-fixture-key" not in json.dumps(command)
    assert "synthetic-fixture-key" not in json.dumps(settings)
    assert "fixture-model" in json.dumps(settings) + json.dumps(child)
    assert env == environment()

def test_custom_case_is_single_resettable_workspace_check():
    collection = json.loads((UNIT / "validation/local-cases.json").read_text())
    assert collection["schema"] == "abb.cases.v1"
    assert len(collection["cases"]) == 1
    steps = collection["cases"][0]["inputs"]
    assert len(steps) == 1 and "Read the file back" in steps[0]["payload"]

def test_outer_recipe_keeps_native_agent_and_unprivileged_user():
    recipe = (UNIT / "Dockerfile").read_text()
    assert "USER agent" in recipe and "COPY .abb-runtime/" in recipe
    assert "synthetic-fixture-key" not in recipe
    assert (UNIT / "ground_truth/.gitkeep").is_file()


def test_build_cache_and_resource_controls():
    recipe = (UNIT / "Dockerfile").read_text()
    assert "--mount=type=cache,target=/root/.npm" in recipe
    assert "--maxsockets=4" in recipe
    assert "npm cache clean" not in recipe


def test_readme_explicitly_selects_actual_local_sdk():
    text = (UNIT / "README.md").read_text()
    assert "agentbench evaluate easy-agent --sdk local --cases 1" in text
    assert "resources/agents/78-easy-agent/validation/run_smoke.py" in text
    assert "8192" in text and "2048" in text
    assert "stock Judge" in text and "does not import" in text
    assert "--case-file" not in text

def smoke_driver():
    spec = importlib.util.spec_from_file_location("smoke_526", UNIT / "validation/run_smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_host_transport_changes_headers_only(tmp_path):
    import io
    import urllib.request
    from urllib.response import addinfourl
    from email.message import Message
    seen = []
    class LocalCapture(urllib.request.BaseHandler):
        handler_order = 1
        def https_open(self, request):
            seen.append((request.data, request.get_header("Authorization"), request.get_header("User-agent")))
            headers = Message(); headers["Content-Type"] = "application/json"
            response = addinfourl(io.BytesIO(b'{"unchanged":true}'), headers, request.full_url, code=200)
            response.msg = "OK"
            return response
    payload = b'{"model":"glm-5.3-flash","max_tokens":2048,"messages":[]}'
    driver = smoke_driver()
    opener = driver.http_opener("AgentBehaviorBench/0.1", tmp_path / "network.jsonl", "glm-5.3-flash", LocalCapture())
    request = urllib.request.Request("https://fixture.example/v1/chat/completions", payload, {"Authorization":"Bearer synthetic-fixture-key"})
    with opener.open(request) as response:
        assert response.read() == b'{"unchanged":true}'
    assert seen == [(payload, "Bearer synthetic-fixture-key", "AgentBehaviorBench/0.1")]
    audit = (tmp_path / "network.jsonl").read_text()
    assert "synthetic-fixture-key" not in audit and '"max_tokens":2048' in audit


def test_host_transport_rejects_other_models_before_network(tmp_path):
    import urllib.request
    driver = smoke_driver()
    opener = driver.http_opener("AgentBehaviorBench/0.1", tmp_path / "network.jsonl", "glm-5.3-flash")
    request = urllib.request.Request("https://fixture.example/v1/chat/completions", b'{"model":"another-model"}')
    with pytest.raises(ValueError, match="approved"):
        opener.open(request)


def test_standard_command_uses_the_real_cli_parser():
    from agentbench.cli.main import build_parser
    args = build_parser().parse_args(["evaluate", "easy-agent", "--sdk", "local", "--cases", "1", "--case-retries", "0", "--model", "glm-5.3-flash", "--no-view"])
    assert args.sdk == "local" and args.cases == 1
    assert args.case_file is None and args.judge is None

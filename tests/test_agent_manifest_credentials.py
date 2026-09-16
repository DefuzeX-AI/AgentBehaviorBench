"""Model credential ownership is deterministic even when extraction mislabels it."""

from copy import deepcopy

import pytest

from agentbench.runtime.agentcontainer.config import tomllib
from tests.agent_build_fixtures import source, plan, Client, build
from tests.test_agent_manifest_generation import facts


@pytest.mark.parametrize("env_keys,secret_keys", [
    (["TAVILY_API_KEY"], ["OPENAI_API_KEY", "GEMINI_API_KEY"]),
    ([], ["TAVILY_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]),
])
def test_reported_company_credential_classifications_are_normalized_without_retry(
        source, plan, facts, env_keys, secret_keys):
    facts["env_keys"], facts["secret_env_keys"] = env_keys, secret_keys
    facts["models"].append({"protocol": "gemini-content", "agent_env": "GEMINI_API_KEY", "endpoint": None})
    original = deepcopy(facts)

    def extracted(payload):
        if payload.get("target_path") == "agent.toml":
            return {"status": "complete", "summary": "Captured credential categorization",
                    "evidence": plan["evidence"], "missing_information": [],
                    "path": "agent.toml", "facts": facts}

    client = Client(plan, callback=extracted)
    assert build(source, plan, client=client).status == "generated"
    generated = tomllib.loads((source.directory / "agent.toml").read_text())
    assert generated["runtime"]["secret_env_keys"] == ["TAVILY_API_KEY"]
    assert generated["runtime"].get("env_keys", []) == []
    assert {item["agent_env"] for item in generated["llm_interception"]["credentials"]} == {
        "OPENAI_API_KEY", "GEMINI_API_KEY"}
    assert sum(request.get("target_path") == "agent.toml" for request in client.requests) == 1
    assert facts == original


def test_environment_ownership_uses_declared_models_not_hardcoded_names():
    from agentbench.onboarding.build_agent_env.build_toml.environment import runtime_environment
    interception = {"credentials": [{"agent_env": "CUSTOM_MODEL_AUTH"}]}
    assert runtime_environment(
        ["CUSTOM_MODEL_AUTH", "APP_REGION", "TOOL_TOKEN", "APP_REGION", "PRIVATE_VALUE"],
        ["CUSTOM_MODEL_AUTH", "PRIVATE_VALUE", "TOOL_TOKEN", "TOOL_TOKEN"], interception
    ) == {"env_keys": ["APP_REGION"], "secret_env_keys": ["PRIVATE_VALUE", "TOOL_TOKEN"]}


def test_undeclared_model_like_names_are_not_silently_discarded():
    from agentbench.onboarding.build_agent_env.build_toml.environment import runtime_environment
    assert runtime_environment(["OPENAI_API_KEY", "APP_REGION"], [], None) == {
        "env_keys": ["APP_REGION"], "secret_env_keys": ["OPENAI_API_KEY"]}

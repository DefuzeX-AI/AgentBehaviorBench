"""Network permissions come from verified client usage, not secret names."""
import copy
from types import SimpleNamespace
import pytest
from tests.agent_build_fixtures import source, plan, Client, write
from agentbench.onboarding.build_agent_env.build_toml.service import render_response
from agentbench.onboarding.build_agent_env.build_toml.validation import validate_manifest
from agentbench.runtime.agentcontainer.config import tomllib


def response(plan):
    value = Client(plan).generate({"target_path": "agent.toml", "response_kind": "configuration_facts"}, prompt="", schema={})
    value["facts"].update(secret_env_keys=["TAVILY_API_KEY"], models=[{
        "protocol": "openai-chat", "agent_env": "OPENAI_API_KEY", "endpoint": None}])
    return value


def session(source, plan, content):
    return SimpleNamespace(source=source, agent_id="my-agent", manifest_options=None, plan=plan,
        context={"files": [{"path": "src/pkg/tools.py", "content": content, "truncated": False}]})


def test_missing_routes_use_actual_calls_not_all_provider_capabilities(source, plan):
    code = "from tavily import AsyncTavilyClient as Client\nclass Tools:\n def __init__(self):\n  self.client = Client(api_key=key)\n async def run(self):\n  await self.client.search('q')\n  await self.client.extract('url')\n"
    request = response(plan)
    before = copy.deepcopy(request)
    current = session(source, plan, code)
    text = render_response(request, current)
    validate_manifest(text, current)
    routes = tomllib.loads(text)["llm_interception"]["tool_routes"]
    assert {path for route in routes for path in route["path_patterns"]} == {"/search", "/extract"}
    assert all(route["host_patterns"] == ["api.tavily.com"] and route["methods"] == ["POST"] for route in routes)
    assert request == before


@pytest.mark.parametrize("code", [
    "from tavily import AsyncTavilyClient\nclient = AsyncTavilyClient(api_key=key, api_base_url=url)\nclient.search('q')",
    "TAVILY_API_KEY = 'placeholder'\n",
    "from tavily import AsyncTavilyClient\nclient = AsyncTavilyClient(api_key=key)\nclient = another_client\nclient.search('q')",
    "client = unrelated_client\nclient.search('q')",
])
def test_ambiguous_or_custom_clients_do_not_gain_standard_routes(source, plan, code):
    text = render_response(response(plan), session(source, plan, code))
    assert not tomllib.loads(text)["llm_interception"].get("tool_routes")


def test_unit_relative_planned_binding_is_normalized_for_manifest(source, plan):
    plan["bindings"] = ["bindings/bridge.py"]
    current = session(source, plan, "")
    value = response(plan)
    value["facts"]["secret_env_keys"] = []
    value["facts"]["adapter"]["binding"] = "bindings/bridge.py:create_graph"
    text = render_response(value, current)
    validate_manifest(text, current)
    assert tomllib.loads(text)["adapter"]["binding"] == "bridge.py:create_graph"

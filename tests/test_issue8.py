"""Issue #8: allow the official release check without opening other GitHub APIs."""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from agentbench.sdk.common.whitelist import load_whitelist


@pytest.mark.parametrize('host,path,method,allowed', [
    ('api.github.com', '/repos/DefuzeX-AI/KUMA-DefuzeX/releases/latest', 'GET', True),
    ('api.github.com', '/repos/DefuzeX-AI/KUMA-DefuzeX/releases/latest', 'POST', False),
    ('api.github.com', '/user', 'GET', False),
    ('unrelated.example', '/repos/DefuzeX-AI/KUMA-DefuzeX/releases/latest', 'GET', False),
])
def test_release_whitelist_uses_real_interceptor_policy(monkeypatch, host, path, method, allowed):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root/'agentbench/services/model-interceptor/src'))
    from defuzex_model_interceptor.routing.policy import EgressPolicy
    routes = load_whitelist(root/'agentbench/sdk/plugin/kuma/whitelist.json')
    policy = EgressPolicy(NS(routes=[], tool_routes=[NS(**r) for r in routes]))
    assert policy.permits_tool(NS(pretty_host=host, path=path, method=method, port=443)) is allowed

"""KUMA-specific discovery uses its official client without leaking credentials."""

import pytest

from agentbench.sdk.plugin.kuma.onboarding_catalog import fetch
from tests.kuma_catalog_fixtures import context


def test_discovery_calls_official_catalog_api_with_explicit_environment(monkeypatch):
    import kuma
    from kuma.repository.strategy_groups import validate_strategy_group_catalog
    calls = []

    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def strategy_group_catalog(self):
            calls.append("catalog GET")
            return validate_strategy_group_catalog(context()["strategy_group_catalog"])

    monkeypatch.setattr(kuma, "KumaClient", Client)
    result = fetch(environ={"KUMA_API_KEY": "key-for-test", "DEFUZEX_API_KEY": "other-key",
                            "KUMA_BASE_URL": "https://catalog.example.invalid"}, timeout=7)
    assert calls == [{"api_key": "key-for-test", "base_url": "https://catalog.example.invalid", "timeout": 7}, "catalog GET"]
    assert result == context()
    assert "key-for-test" not in str(result)


def test_discovery_keeps_bba_key_alias_and_sdk_default_url(monkeypatch):
    import kuma
    from kuma.repository.strategy_groups import validate_strategy_group_catalog
    calls = []

    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def strategy_group_catalog(self):
            return validate_strategy_group_catalog(context()["strategy_group_catalog"])

    monkeypatch.setattr(kuma, "KumaClient", Client)
    fetch(environ={"DEFUZEX_API_KEY": "alias-key"}, timeout=3)
    assert calls[0] == {"api_key": "alias-key", "base_url": kuma.DEFAULT_BASE_URL, "timeout": 3}


def test_discovery_failures_do_not_include_raw_server_or_credential_text(monkeypatch):
    import kuma
    secret = "private-catalog-key-123"

    class Client:
        def __init__(self, **kwargs):
            raise RuntimeError("HTTP failed with Authorization: " + secret)

    monkeypatch.setattr(kuma, "KumaClient", Client)
    with pytest.raises(ValueError, match="Could not refresh") as error:
        fetch(environ={"KUMA_API_KEY": secret}, timeout=3)
    assert secret not in str(error.value)


def test_missing_key_is_reported_before_a_catalog_request(monkeypatch):
    import kuma
    monkeypatch.setattr(kuma, "KumaClient", lambda **kwargs: pytest.fail("unexpected client"))
    with pytest.raises(ValueError, match="KUMA_API_KEY or DEFUZEX_API_KEY"):
        fetch(environ={}, timeout=3)


def test_declared_file_policy_enables_official_casegen_capability(monkeypatch):
    import kuma
    from kuma.repository.strategy_groups import validate_strategy_group_catalog
    class Client:
        def __init__(self, **kwargs): pass
        def strategy_group_catalog(self):
            return validate_strategy_group_catalog(context()['strategy_group_catalog'])
    monkeypatch.setattr(kuma, 'KumaClient', Client)
    result = fetch(environ={'KUMA_API_KEY':'test-only'}, timeout=3, evaluation={
        'workspace': {'path':'/home/agent/workspace','initial_state':'empty'},
        'file_evidence': {'track_files':True,'upload_diff':True}})
    assert 'file_change' in result['available_evidence_capabilities']

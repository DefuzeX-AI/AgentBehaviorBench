"""The Watchtower outer binding must enforce its declared scan scope."""

from __future__ import annotations

import sys
from types import ModuleType
from urllib.parse import urlsplit

import pytest

from tests.registered_agents import binding


@pytest.fixture
def watchtower(monkeypatch):
    module = binding("watchtower")

    targets = ModuleType("watchtower.core.targets")
    def extract_hostname(value):
        try:
            return urlsplit(value if "://" in value else f"//{value}").hostname or ""
        except ValueError:
            return ""

    targets.extract_hostname = extract_hostname
    targets.normalize_url = lambda value: value if "://" in value else f"https://{value}"
    guardrails = ModuleType("watchtower.core.guardrails")
    guardrails.validate_target = lambda value: value.startswith(("http://", "https://"))

    package = ModuleType("watchtower")
    core = ModuleType("watchtower.core")
    monkeypatch.setitem(sys.modules, "watchtower", package)
    monkeypatch.setitem(sys.modules, "watchtower.core", core)
    monkeypatch.setitem(sys.modules, "watchtower.core.targets", targets)
    monkeypatch.setitem(sys.modules, "watchtower.core.guardrails", guardrails)
    return module


@pytest.mark.parametrize("target", ["127.0.0.1", "localhost"])
def test_only_container_loopback_targets_are_accepted(watchtower, target):
    assert watchtower.target_from_input(f"Scan http://{target} for open services") == f"http://{target}"


@pytest.mark.parametrize("target", ["example.com", "192.168.1.1", "10.0.0.1", "[::1]", "[::ffff:127.0.0.1]"])
def test_external_and_private_network_targets_are_rejected(watchtower, target):
    with pytest.raises(ValueError, match="limited to the Agent container loopback"):
        watchtower.target_from_input(f"Scan http://{target} for open services")


def test_userinfo_does_not_hide_a_non_loopback_host(watchtower):
    with pytest.raises(ValueError, match="limited to the Agent container loopback"):
        watchtower.target_from_input("Scan http://127.0.0.1@example.com for open services")


def test_official_style_task_without_target_never_scans(watchtower):
    graph = watchtower.WatchtowerGraph()
    graph._load = lambda: None
    state = graph.invoke("Assess whether requests 2.30.0 is affected by CVE-2023-32681")

    assert state["scope_targets"] == []
    assert state["is_finished"] is True
    assert state["observations"][0]["tool"] == "input-validation"
    assert "No scan performed" in state["observations"][0]["output"]

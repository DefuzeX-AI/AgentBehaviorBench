"""Issue #137: non-model egress goes to its own observer service and event stream."""
import json
from types import SimpleNamespace

import pytest

from agentbench.runtime.docker.egress_observer import (
    EGRESS_PREFIX, EgressObserverPolicy, OBSERVER_PORT, observer_configuration)
from agentbench.runtime.docker.policy import DEFAULT_EGRESS_ALLOW, DockerPolicy, EgressSettings
from agentbench.runtime.docker.runtime import DockerRuntime
from agentbench.runtime.interception.service_config import prepare_service_config
from agentbench.runtime.interception.trace import TraceEvent


def test_default_policy_observes_egress_and_admits_package_registries():
    settings = DockerPolicy().egress
    assert settings.mode == "observe"
    rules = {rule["host"]: rule["ports"] for rule in settings.rules()}
    assert set(rules) == set(DEFAULT_EGRESS_ALLOW)
    assert rules["pypi.org"] == [80, 443] and "example.com" not in rules


def test_environment_can_deny_or_extend_the_allowlist():
    assert EgressSettings.from_environment({"ABB_EGRESS": "deny"}).mode == "deny"
    extended = EgressSettings.from_environment({"ABB_EGRESS_ALLOW": "github.com, *.example.org:8443"})
    rules = {rule["host"]: rule["ports"] for rule in extended.rules()}
    assert rules["github.com"] == [80, 443] and rules["*.example.org"] == [8443]
    assert EgressSettings.from_environment({}, EgressSettings(allow=())).rules() == []


@pytest.mark.parametrize("entry", ["*", "a*.org", "host/path", "host:0", "host:x"])
def test_unsafe_allow_entries_are_rejected(entry):
    with pytest.raises(ValueError):
        EgressSettings(allow=(entry,))
    with pytest.raises(ValueError):
        EgressSettings(mode="open")


def test_observer_configuration_and_interceptor_handoff_address(tmp_path):
    config = json.loads(observer_configuration("agent", EgressSettings(allow=("pypi.org",))))
    assert config == {"agent_id": "agent", "listen_port": OBSERVER_PORT,
                      "allow": [{"host": "pypi.org", "ports": [80, 443]}]}
    interception = SimpleNamespace(mode="observe", observation_headers={}, observation_tool_purposes={},
                                   routes=(), tool_routes=(), token_counting={}, credentials=())
    common = dict(agent_id="agent", max_trace_bytes=4096, secret_dir=tmp_path, secret_resolver=None, environ={})
    data, _ = prepare_service_config(interception, **common)
    assert "egress_proxy" not in data
    data, _ = prepare_service_config(interception, egress_proxy=("observer", 3128), **common)
    assert data["egress_proxy"] == {"host": "observer", "port": 3128}


def test_observer_container_is_unprivileged():
    arguments = EgressObserverPolicy(dns_servers=("1.1.1.1",)).run_arguments()
    assert "--cap-drop=ALL" in arguments and "--read-only" in arguments
    assert not any("NET_ADMIN" in argument or "NET_RAW" in argument for argument in arguments)
    assert arguments[-2:] == ("--dns", "1.1.1.1")


def test_start_egress_observer_creates_labelled_container_with_its_allowlist(tmp_path):
    runtime = DockerRuntime(environ={"ABB_EGRESS_ALLOW": "github.com"}, artifact_root=tmp_path, run_id="run")
    created = []
    runtime._egress_observer_images = SimpleNamespace(resolve_image=lambda: "egress-image")
    runtime._run = lambda *args, **kwargs: None
    runtime._create_resource = lambda kind, name, arguments, deadline: created.append(arguments)
    runtime._wait_for_egress_observer = lambda name, deadline=None: None
    runtime._follow_egress = lambda name: (SimpleNamespace(), SimpleNamespace(join=lambda timeout: None))
    observer = runtime._start_egress_observer(agent_id="agent", suffix="abc", network_name="net")
    assert (observer.container_name, observer.port) == ("defuzex-abc-egress-observer", OBSERVER_PORT)
    command = created[0]
    assert command[command.index("--network") + 1] == "net" and command[-1] == "egress-image"
    assert "abb.role=egress-observer" in command
    config = json.loads(next(item for item in command if item.startswith("ABB_EGRESS_CONFIG="))
                        .split("=", 1)[1])
    assert {"host": "github.com", "ports": [80, 443]} in config["allow"]


def test_egress_events_use_their_own_prefix_and_file(tmp_path):
    line = EGRESS_PREFIX + json.dumps({"event": "egress_denied", "conn_id": "egress_1", "host": "example.com"})
    assert TraceEvent.from_log_line(line) is None  # never parsed as a model trace event
    event = TraceEvent.from_log_line(line, prefix=EGRESS_PREFIX)
    runtime = DockerRuntime(environ={}, artifact_root=tmp_path, run_id="run", identity={"case_index": 3})
    runtime._egress_event_sink().emit(event)
    row = json.loads((tmp_path / "egress.jsonl").read_text())
    assert (row["source"], row["event"], row["data"]["host"]) == ("egress-observer", "egress_denied", "example.com")
    assert row["data"]["case_index"] == 3
    assert not (tmp_path / "network.jsonl").exists()

"""Opt-in real Docker acceptance for two Cases of one Agent and owned cancellation.

Run with ABB_DOCKER_CASE_BASE_IMAGE pointing to an available Python image
with a non-root `agent` user. No external SDK or provider credentials are used.
"""

from __future__ import annotations

import json
import hashlib
import os
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agentbench.adapter import AdapterInvocation
from agentbench.harness.concurrency import ConcurrencySettings
from agentbench.harness.registry import AgentRegistration
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult
from agentbench.harness.runner.suite_runner import SuiteRunner
from agentbench.runtime.docker.command import DockerCommandRunner
from agentbench.runtime.docker.policy import DockerPolicy
from agentbench.runtime.docker.interceptor_policy import InterceptorPolicy
from agentbench.runtime.services import RuntimeServices
from agentbench.observe.store import TraceStore


@pytest.fixture
def upstream(tmp_path, intercept):
    if not intercept:
        yield None
        return
    key, certificate = tmp_path / "mock.key", tmp_path / "mock.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=host.docker.internal", "-addext", "subjectAltName=DNS:host.docker.internal",
        "-keyout", str(key), "-out", str(certificate),
    ], capture_output=True, check=True, timeout=15)
    configuration = tmp_path / "config.yaml"
    configuration.write_text("ssl_verify_upstream_trusted_ca: /run/acceptance-ca/mock.pem\n")
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["content-length"])))
            marker = payload["messages"][0]["content"]
            requests.append({"path": self.path, "marker": marker, "model": payload["model"]})
            body = json.dumps({
                "id": "chat-" + marker, "object": "chat.completion", "created": 1,
                "model": payload["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello " + marker},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class MockTrustPolicy:
        def run_arguments(self):
            return (*InterceptorPolicy().run_arguments(),
                    "--mount", f"type=bind,source={certificate},target=/run/acceptance-ca/mock.pem,readonly",
                    "--mount", f"type=bind,source={configuration},target=/run/defuzex/ca/config.yaml,readonly")

    try:
        yield SimpleNamespace(
            environ={"OPENROUTER_API_KEY": "offline-mock-secret", "OPENROUTER_MODEL": "offline-mock",
                     "OPENROUTER_BASE_URL": f"https://host.docker.internal:{server.server_port}/v1"},
            policy=MockTrustPolicy(), requests=requests,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.skipif(not os.environ.get("ABB_DOCKER_CASE_BASE_IMAGE"),
                    reason="Set ABB_DOCKER_CASE_BASE_IMAGE for real Docker acceptance")
@pytest.mark.parametrize("cancel", [False, True], ids=["two_cases", "cancel_two_cases"])
@pytest.mark.parametrize("intercept", [False, True], ids=["agent_only", "paired_interceptors"])
def test_one_agent_runs_two_cases_in_parallel_and_cleans_resources(cancel, intercept, upstream):
    from agentbench.sdk.contracts import PreparedCase

    base = os.environ["ABB_DOCKER_CASE_BASE_IMAGE"]
    output = (Path("results/verification") /
              f"docker-cases-{'paired-' if intercept else ''}{'cancel' if cancel else 'run'}-{uuid4().hex}").resolve()
    gate = output / "gate"
    gate.mkdir(parents=True)
    suite_id = f"case_acceptance_{uuid4().hex}"
    commands = DockerCommandRunner()
    requested_cases = 3 if cancel else 2
    case_ids = tuple(f"case-marker-{index}" for index in range(requested_cases))
    agent_id = "single-agent-case-acceptance"
    root = output / "agent"
    root.mkdir()
    (root / "Dockerfile").write_text(
        f"FROM {base}\nUSER root\nWORKDIR /opt/agent\nCOPY main.py /opt/agent/main.py\nUSER agent\n")
    model_call = (
        "import urllib.request, ssl\n"
        "body = json.dumps({'model': 'source-model', 'messages': [{'role': 'user', 'content': marker}]}).encode()\n"
        "request = urllib.request.Request('https://api.openai.com/v1/chat/completions', data=body, "
        "headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']})\n"
        "with urllib.request.urlopen(request, timeout=20, context=ssl.create_default_context(cafile=os.environ['SSL_CERT_FILE'])) as response:\n"
        "    answer = json.load(response)['choices'][0]['message']['content']\n"
        "assert answer == 'hello ' + marker, answer\n"
        "print(json.dumps({'model_answer': answer}), flush=True)\n"
    ) if intercept else ""
    (root / "main.py").write_text(
        "import json, pathlib, os, time\n"
        "marker = os.environ['ABB_ACCEPTANCE_CASE_MARKER']\n"
        "print(json.dumps({'case_id': marker, 'status': 'waiting'}), flush=True)\n"
        + model_call +
        "deadline = time.monotonic() + 90\n"
        "while not pathlib.Path('/run/acceptance-gate/release').exists():\n"
        "    if time.monotonic() > deadline: raise TimeoutError('acceptance gate')\n"
        "    time.sleep(0.05)\n"
        "print(json.dumps({'case_id': marker, 'output': 'hello ' + marker}), flush=True)\n")
    (root / "agent.toml").write_text(
        f'schema_version = "defuzex-bench.agent.v2"\nagent_id = "{agent_id}"\nframework = "fixture"\n'
        '[runtime]\ntype = "docker"\ntimeout_sec = 90\nenv_keys = ["ABB_ACCEPTANCE_CASE_MARKER"]\n'
        '[build]\ncontext = "."\ndockerfile = "Dockerfile"\n'
        '[launch]\nargv = ["python", "/opt/agent/main.py"]\n')
    if intercept:
        with (root / "agent.toml").open("a") as manifest:
            manifest.write(
                '[llm_interception]\nrequired = true\ntrust_plugin = "pem-env"\n'
                '[[llm_interception.credentials]]\nid = "openai"\nagent_env = "OPENAI_API_KEY"\nauth_plugin = "bearer-token"\n'
                '[[llm_interception.routes]]\nid = "openai-chat"\nhost_patterns = ["api.openai.com"]\n'
                'ports = [443]\nmethods = ["POST"]\npath_patterns = ["/v1/chat/completions"]\n'
                'protocol_plugin = "openai-chat"\ncredential = "openai"\n')
    registration = AgentRegistration(agent_id, root, True, "ready", "fixture", "offline-acceptance",
                                     case_count=requested_cases)

    class GatePolicy:
        def run_arguments(self):
            return (*DockerPolicy().run_arguments(), "--mount",
                    f"type=bind,source={gate},target=/run/acceptance-gate,readonly")

    class Factory:
        supports_concurrency = True

        def __init__(self):
            self.services = RuntimeServices(environ={**os.environ, **(upstream.environ if upstream else {})})
            self.control = None
            self.lock = threading.Lock()
            self.started = []
            self.both_started = threading.Event()
            self.traces = {}
            self.runner_uses = []
            self.prepare_count = 0
            self.identities = {}

        def open_suite(self, actual_suite_id, control):
            assert actual_suite_id == suite_id
            self.control = control
            return self

        def create(self, registration, identity, trace_sink):
            owner = self

            class Runner:
                used = None

                def validate_sdk(self, registration):
                    return "offline-real-docker-cases"

                def prepare_cases(self, registration, **callbacks):
                    assert self.used is None, "Preparation runner must belong only to its task"
                    self.used = "prepare"
                    owner.prepare_count += 1
                    owner.runner_uses.append((self, "prepare"))
                    cases = []
                    for index, case_id in enumerate(case_ids):
                        path = output / f"{case_id}.prepared.json"
                        content = json.dumps({"case_id": case_id, "case_index": index, "input": case_id})
                        path.write_text(content)
                        cases.append(PreparedCase(case_index=index, case_id=case_id, artifact_path=path,
                                                  content_sha256=hashlib.sha256(content.encode()).hexdigest()))
                    return tuple(cases)

                def run_case(self, registration, case, **callbacks):
                    assert self.used is None, "Each Case requires a fresh runner"
                    self.used = "execute"
                    owner.runner_uses.append((self, "execute"))
                    marker = case.case_id
                    assert marker == case_ids[case.case_index]
                    assert identity["case_index"] == case.case_index
                    assert identity["case_id"] == marker
                    assert identity["agent_job_id"] and identity["job_id"]
                    payload = json.loads(case.artifact_path.read_text())
                    assert payload["input"] == marker
                    directory = output / marker
                    directory.mkdir(exist_ok=True)
                    store = TraceStore(directory / "network.jsonl", f"run-{marker}",
                                       context=identity, environ=owner.services.environ)

                    class Sink:
                        def emit(self, event):
                            store.emit(event)
                            with owner.lock:
                                owner.traces.setdefault(marker, []).append(event)

                    runtime = owner.services.create_docker_runtime(
                        control=owner.control, identity=identity, policy=GatePolicy(),
                        environ={**owner.services.environ, "ABB_ACCEPTANCE_CASE_MARKER": marker},
                        interceptor_policy=upstream.policy if upstream else None, trace_sink=Sink(),
                        artifact_root=directory, run_id=f"run-{marker}")
                    session = None
                    record = {**identity, "started_at": time.monotonic()}
                    try:
                        session = runtime.start(registration)
                        with owner.lock:
                            owner.started.append(marker)
                            owner.identities[marker] = dict(identity)
                            if len(owner.started) == 2:
                                owner.both_started.set()
                        if callbacks.get("on_step_start"):
                            callbacks["on_step_start"](registration.agent_id, "input-1", marker)
                        assert session.wait(timeout=90) == 0
                        if intercept:
                            session.validate_trace(0)
                        lines = [json.loads(line) for line in session.stdout.splitlines() if line.startswith("{")]
                        value = lines[-1]["output"]
                        assert lines[-1]["case_id"] == marker and value == "hello " + marker
                        record.update(status="succeeded", case=payload, output=value,
                                      judge={"case_id": marker, "status": "pass"})
                        step = BenchmarkStepResult("input-1", marker,
                                                   AdapterInvocation(output=value, raw_output=value))
                        if callbacks.get("on_step_complete"):
                            callbacks["on_step_complete"](registration.agent_id, step)
                        return BenchmarkResult(registration.agent_id, "offline-real-docker-case", identity["job_id"],
                                               "completed", SimpleNamespace(status="pass"), (step,), 1)
                    except BaseException as exc:
                        record.update(status="cancelled" if owner.control.cancelled else "failed",
                                      error_type=type(exc).__name__, error=str(exc))
                        raise
                    finally:
                        try:
                            if session is not None:
                                session.close()
                                record.update(stdout=session.stdout, stderr=session.stderr,
                                              returncode=session.returncode, cleanup_status="removed")
                        finally:
                            record["ended_at"] = time.monotonic()
                            (directory / "run.json").write_text(json.dumps(record, indent=2))

            return Runner()

        def close(self):
            self.services.close()

    factory = Factory()
    suite = SuiteRunner(runner_factory=factory, concurrency=ConcurrencySettings(max_parallel_cases=2))
    observed = []
    network_modes = {}
    controller_errors = []
    events = []

    def controller():
        try:
            assert factory.both_started.wait(75), "Two Cases of the single Agent did not start"
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                listed = commands.run(["ps", "--filter", f"label=abb.suite_id={suite_id}",
                                       "--format", "{{.Names}}"], timeout=5)
                assert listed.returncode == 0, listed.stderr
                names = listed.stdout.splitlines()
                if len(names) == (4 if intercept else 2):
                    observed.extend(names)
                    break
                time.sleep(0.1)
            assert len(observed) == (4 if intercept else 2), "Expected two simultaneously running Cases"
            inspected = commands.run(["inspect", *observed], timeout=10)
            assert inspected.returncode == 0, inspected.stderr
            for container in json.loads(inspected.stdout):
                network_modes[container["Name"].lstrip("/")] = {
                    "id": container["Id"], "labels": container["Config"]["Labels"],
                    "network_mode": container["HostConfig"]["NetworkMode"], "image_id": container["Image"],
                }
            if intercept:
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    with factory.lock:
                        completed = sum(any(event.event == "llm_response" for event in trace)
                                        for trace in factory.traces.values())
                    if completed == 2:
                        break
                    time.sleep(0.1)
                assert completed == 2, "Both Cases must persist their own intercepted model response"
            if cancel:
                suite.cancel()
            else:
                (gate / "release").write_text("release both Cases\n")
        except BaseException as exc:
            controller_errors.append(repr(exc))
            suite.cancel()

    controller_thread = threading.Thread(target=controller, daemon=True)
    controller_thread.start()
    started_at = time.monotonic()
    result = suite.run((registration,), suite_id=suite_id, on_event=events.append)
    controller_thread.join(timeout=3)
    assert not controller_thread.is_alive()
    snapshot = factory.services.resource_registry.snapshot()
    containers = commands.run(["ps", "--all", "--filter", f"label=abb.suite_id={suite_id}",
                               "--format", "{{.Names}}"], timeout=10)
    networks = commands.run(["network", "ls", "--filter", f"label=abb.suite_id={suite_id}",
                             "--format", "{{.Name}}"], timeout=10)
    item = result.items[0]
    case_results = [dict(agent_id=case.agent_id, case_index=case.case_index, case_id=case.case_id,
                         job_id=case.job_id, status=case.status,
                         error_type=case.error_type, error_message=case.error_message)
                    for case in item.case_results]
    evidence = {
        "suite_id": suite_id, "selected_agents": 1, "requested_cases": requested_cases,
        "max_parallel_cases": 2, "cancelled": cancel,
        "actual_interceptors": intercept, "network_modes": network_modes,
        "local_mock_requests": upstream.requests if upstream else [],
        "observed_simultaneous_containers": observed, "started_cases": factory.started,
        "case_identities": factory.identities, "prepare_count": factory.prepare_count,
        "elapsed_seconds": time.monotonic() - started_at,
        "attempted_agents": result.attempted_count, "passed_agents": result.passed_count,
        "attempted_cases": item.attempted_case_count, "completed_cases": item.completed_case_count,
        "skipped_cases": item.skipped_case_count,
        "controller_errors": controller_errors, "resources": snapshot,
        "remaining_containers": containers.stdout.splitlines(),
        "remaining_networks": networks.stdout.splitlines(), "case_results": case_results,
        "events": [{key: event[key] for key in ("event", "agent_id", "agent_job_id", "job_id",
                                               "case_index", "case_id", "status") if key in event}
                   for event in events],
    }
    (output / "acceptance.json").write_text(json.dumps(evidence, indent=2))
    assert not controller_errors, controller_errors
    assert result.selected_count == result.attempted_count == 1
    assert len(observed) == (4 if intercept else 2) and set(factory.started) == set(case_ids[:2])
    assert factory.prepare_count == 1
    assert len(factory.runner_uses) == 3
    assert len({id(runner) for runner, _ in factory.runner_uses}) == 3
    assert {identity["agent_id"] for identity in factory.identities.values()} == {agent_id}
    assert len({identity["agent_job_id"] for identity in factory.identities.values()}) == 1
    assert len({identity["job_id"] for identity in factory.identities.values()}) == 2
    assert len(snapshot) == (6 if intercept else 4) and all(resource["status"] == "removed" for resource in snapshot)
    assert containers.returncode == networks.returncode == 0
    assert not containers.stdout.strip() and not networks.stdout.strip()
    execution_containers = [container for container in network_modes.values()
                            if container["labels"]["abb.role"] == "agent"]
    assert len(execution_containers) == 2
    assert len({container["image_id"] for container in execution_containers}) == 1
    if intercept:
        assert {request["marker"] for request in upstream.requests} == set(case_ids[:2])
        assert all(request["model"] == "offline-mock" for request in upstream.requests)
        call_ids = []
        for marker in case_ids[:2]:
            trace = factory.traces[marker]
            assert {event.data["agent_id"] for event in trace} == {agent_id}
            requests = [event for event in trace if event.event == "llm_request"]
            responses = [event for event in trace if event.event == "llm_response"]
            assert len(requests) == len(responses) == 1
            assert requests[0].data["call_id"] == responses[0].data["call_id"]
            call_ids.append(requests[0].data["call_id"])
            assert marker in json.dumps(requests[0].data)
            persisted = (output / marker / "network.jsonl").read_text()
            assert marker in persisted
            assert all(other not in persisted for other in case_ids if other != marker)
            rows = [json.loads(line) for line in persisted.splitlines()]
            assert {row["data"]["case_id"] for row in rows} == {marker}
            assert {row["data"]["job_id"] for row in rows} == {factory.identities[marker]["job_id"]}
        assert len(set(call_ids)) == 2
        for container in execution_containers:
            peers = [peer for peer in network_modes.values()
                     if peer["labels"]["abb.role"] == "interceptor"
                     and peer["labels"]["abb.job_id"] == container["labels"]["abb.job_id"]]
            assert len(peers) == 1
            assert container["network_mode"] == "container:" + peers[0]["id"]
    assert [case.case_index for case in item.case_results] == list(range(requested_cases))
    terminal_events = [event for event in events if event["event"] == "case_completed"]
    assert len(terminal_events) == requested_cases
    assert {event["case_id"] for event in terminal_events} == set(case_ids)
    if cancel:
        assert not result.passed and result.failed_count == 1
        assert item.attempted_case_count == 2 and item.skipped_case_count == 1
        assert [case.status for case in item.case_results] == ["cancelled", "cancelled", "skipped"]
        assert item.error_type == "RunCancelled"
        assert all(case.error_type == "RunCancelled" for case in item.case_results[:2])
        assert not (output / case_ids[2] / "run.json").exists()
    else:
        assert result.passed and result.passed_count == 1
        assert item.completed_case_count == item.attempted_case_count == 2
        assert len(item.benchmarks) == 2 and all(benchmark.passed for benchmark in item.benchmarks)
        assert [benchmark.steps[0].payload for benchmark in item.benchmarks] == list(case_ids)
        assert [benchmark.steps[0].invocation.output for benchmark in item.benchmarks] == [
            "hello " + marker for marker in case_ids]
    print(f"Real Docker Case concurrency acceptance: {output}")

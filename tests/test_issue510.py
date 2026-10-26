"""StructureClaw packaging and native transport regressions."""
import importlib.util
import json
from pathlib import Path
import shutil
import tomllib

import pytest

from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from agentbench.runtime.source.preparation import prepare_agent_source

UNIT = Path(__file__).resolve().parents[1] / "resources/agents/127-structureclaw"


def bridge():
    spec = importlib.util.spec_from_file_location("structureclaw_bridge", UNIT / "bindings/bridge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fresh_package_preparation_and_binding_contract(tmp_path):
    root = tmp_path / "unit"
    shutil.copytree(UNIT, root, ignore=shutil.ignore_patterns("agent", "node_modules", "__pycache__"))
    prepare_agent_source(root, cache_dir=tmp_path / "cache")
    assert (root / "agent/package-lock.json").read_bytes() == (root / "install/package-lock.json").read_bytes()
    config = LangGraphAdapterConfig.from_agent_dir(root)
    assert config.binding == "bridge.py:create_graph"
    assert config.output_key == "response"
    manifest = tomllib.loads((root / "agent.toml").read_text())
    assert "model" not in manifest
    lock = json.loads((root / "agent/package-lock.json").read_text())
    assert lock["packages"]["node_modules/@structureclaw/structureclaw"]["version"] == "1.1.0"


def test_invalid_input_never_starts_process(monkeypatch):
    module = bridge()
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid input must not launch a native process")
    monkeypatch.setattr(module.subprocess, "Popen", unexpected)
    graph = module.create_graph()
    for value in (None, {}, {"message": " "}, {"message": 5}):
        with pytest.raises(ValueError, match="nonempty message"):
            graph.invoke(value)


def test_transport_preserves_context_state_and_interceptor_environment(monkeypatch):
    module = bridge()
    for key, value in {"LLM_API_KEY": "test-secret", "LLM_BASE_URL": "https://example.invalid/v1", "LLM_MODEL": "test-model"}.items():
        monkeypatch.setenv(key, value)
    seen = {}
    result = {"response": "native", "state": {"messages": [{"tool_calls": [{"name": "calculate"}]}], "analysisResult": {"native": True}}}
    class Process:
        returncode = 0
        def __init__(self, argv, **kwargs):
            seen.update(kwargs)
            self.output = Path(argv[-1])
        def communicate(self, data=None, timeout=None):
            seen["input"] = json.loads(data)
            self.output.write_text(json.dumps(result))
            return "native logs", ""
        def poll(self):
            return 0
    monkeypatch.setattr(module.subprocess, "Popen", Process)
    value = {"message": "Compute", "context": {"locale": "en", "skillIds": ["beam"]}}
    assert module.create_graph().invoke(value, {"configurable": {"thread_id": "case-1"}}) == result
    assert seen["input"] == {"input": {**value, "conversationId": "case-1"}, "resume": False}
    assert seen["env"]["LLM_API_KEY"] == "test-secret"
    assert seen["env"]["LLM_MODEL"] == "test-model"
    assert value == {"message": "Compute", "context": {"locale": "en", "skillIds": ["beam"]}}


def test_native_bridge_keeps_full_upstream_graph():
    source = (UNIT / "bindings/native.mjs").read_text()
    assert "service.runFull(input)" in source
    assert "presentState(state, chunks)" in source
    assert "await prisma.$disconnect()" in source
    assert "new StateGraph" not in source
    assert "enabledToolIds" not in source


def test_native_interrupt_question_is_presented_verbatim():
    import subprocess
    if shutil.which("node") is None:
        pytest.skip("Node is required for the native presentation regression")
    path = (UNIT / "bindings/presentation.mjs").as_uri()
    script = f'''import {{presentState}} from {json.dumps(path)};
const state = {{messages:[{{content:'',tool_calls:[{{name:'ask_user_clarification'}}]}}],
__interrupt__:[{{value:{{question:'What is the span?',options:['4 m','6 m']}}}}]}};
const result = presentState(state);
if(result.response !== 'What is the span?\\n4 m\\n6 m') throw new Error('Clarification lost');
if(result.state !== state) throw new Error('State replaced');
const resumed = presentState({{messages:[{{content:'done'}}]}});
if(resumed.response !== 'done' || resumed.interrupts.length) throw new Error('Resume lost');'''
    subprocess.run(["node", "--input-type=module", "-e", script], check=True)


def test_interrupted_conversation_uses_native_resume_next_turn(monkeypatch):
    module = bridge()
    calls = []
    class Process:
        returncode = 0
        def __init__(self, argv, **kwargs):
            self.output = Path(argv[-1])
        def communicate(self, data=None, timeout=None):
            calls.append(json.loads(data))
            self.output.write_text(json.dumps({"response": "span?", "interrupts": [{"question": "span?"}] if len(calls) == 1 else []}))
            return "", ""
        def poll(self):
            return 0
    monkeypatch.setattr(module.subprocess, "Popen", Process)
    graph = module.create_graph()
    graph.invoke("Build a beam")
    graph.invoke("6 m")
    graph.invoke("Now summarize")
    assert [item["resume"] for item in calls] == [False, True, False]
    assert len({item["input"]["conversationId"] for item in calls}) == 1


def test_native_failure_keeps_error_but_redacts_credentials(monkeypatch):
    module = bridge()
    monkeypatch.setenv("LLM_API_KEY", "private-test-value")
    class Process:
        returncode = 1
        def __init__(self, *args, **kwargs):
            pass
        def communicate(self, *args, **kwargs):
            return "", "upstream auth failure: private-test-value"
        def poll(self):
            return 1
    monkeypatch.setattr(module.subprocess, "Popen", Process)
    with pytest.raises(RuntimeError, match="upstream auth failure") as error:
        module.create_graph().invoke("Compute")
    assert "private-test-value" not in str(error.value)
    assert "[REDACTED]" in str(error.value)

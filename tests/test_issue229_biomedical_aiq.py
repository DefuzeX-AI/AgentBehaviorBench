"""Issue #229: NVIDIA Biomedical AI-Q Agent onboarding contract."""

from __future__ import annotations

import importlib.util
import io
import json
import logging
import asyncio
import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from pathlib import Path

import pytest

from agentbench.harness.registry import load_registry
from agentbench.runtime.agentcontainer.config import tomllib


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources" / "agents" / "49-biomedical-aiq-research-agent"


def _binding():
    spec = importlib.util.spec_from_file_location(
        "issue229_biomedical_binding", UNIT / "bindings" / "bridge.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _context():
    return tomllib.loads((UNIT / "agent.toml").read_text())["adapter"]["context"]


def _payload(**overrides):
    value = {
        "topic": "Cystic fibrosis therapies",
        "report_organization": "Abstract, evidence, limitations, sources",
        "search_web": False,
        "rag_collection": "Biomedical_Dataset",
        "num_queries": 3,
        "llm_name": "nemotron",
    }
    value.update(overrides)
    return value


def test_plain_text_maps_only_topic_onto_declared_upstream_context():
    module = _binding()
    result = json.loads(module._native_input("Cystic fibrosis therapies", _context()))

    assert result == {"topic": "Cystic fibrosis therapies", **_context()}


def test_complete_json_preserves_native_business_fields():
    module = _binding()
    payload = _payload(search_web=True, num_queries=5)

    assert json.loads(module._native_input(json.dumps(payload), _context())) == payload


def test_plain_text_context_does_not_override_topic_with_demo_research_task():
    context = _context()
    assert "cystic fibrosis" not in context["report_organization"].lower()
    assert "gene therapy" not in context["report_organization"].lower()
    value = "Discuss the limitations of the supplied evidence."
    result = json.loads(_binding()._native_input(value, context))
    assert result["topic"] == value
    assert result["report_organization"] == context["report_organization"]


@pytest.mark.parametrize(
    "value,match",
    [
        ("", "non-empty"),
        ("{bad", "invalid"),
        (json.dumps({"topic": "only"}), "missing"),
        (json.dumps(_payload(extra=True)), "unsupported"),
        (json.dumps(_payload(search_web="yes")), "boolean"),
        (json.dumps(_payload(num_queries=0)), "1 through 10"),
        (json.dumps(_payload(llm_name="instruct_llm")), "nemotron"),
    ],
)
def test_invalid_inputs_fail_before_native_execution(value, match):
    with pytest.raises(ValueError, match=match):
        _binding()._native_input(value, _context())


def test_secret_filter_redacts_upstream_virtual_screening_log(monkeypatch):
    module = _binding()
    monkeypatch.setenv("NVIDIA_API_KEY", "nvidia-secret-value")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(module._SecretFilter())
    record = logging.LogRecord(
        "aiq_aira.nodes",
        logging.INFO,
        __file__,
        1,
        "USING NVIDIA_API_KEY: nvidia-secret-value",
        (),
        None,
    )

    handler.handle(record)

    assert "nvidia-secret-value" not in stream.getvalue()
    assert "[REDACTED]" in stream.getvalue()


def test_unit_source_and_registry_are_pinned_to_issue229_revision():
    manifest = tomllib.loads((UNIT / "agent.toml").read_text())
    source = json.loads((UNIT / "source-manifest.json").read_text())
    registration = load_registry(ROOT / "resources" / "registry.toml").find(
        "biomedical-aiq-research-agent", enabled_only=False
    )

    assert manifest["source"]["revision"] == "b5cd7b4c7ae544c1e21ac79ef9fa67641eeff5a4"
    assert source["revision"] == manifest["source"]["revision"]
    assert source["repository"] == manifest["source"]["repository"]
    assert (UNIT / "agent" / "LICENSE").is_file()
    assert registration.path == UNIT
    assert registration.status == "adapting"
    assert registration.enabled is False


def test_manifest_keeps_optional_tools_explicit_and_model_key_intercepted():
    manifest = tomllib.loads((UNIT / "agent.toml").read_text())
    runtime = manifest["runtime"]
    interception = manifest["llm_interception"]

    assert "OPENAI_API_KEY" not in runtime.get("secret_env_keys", [])
    assert interception["credentials"][0]["agent_env"] == "OPENAI_API_KEY"
    hosts = {
        host
        for route in interception["tool_routes"]
        for host in route["host_patterns"]
    }
    assert {
        "rag-server",
        "api.tavily.com",
        "pubchem.ncbi.nlm.nih.gov",
        "search.rcsb.org",
        "files.rcsb.org",
        "health.api.nvidia.com",
    } <= hosts


def test_native_default_workflow_is_selected_and_resources_close(monkeypatch):
    """The pinned Toolkit resolves entry_function only in config.functions."""
    events = []

    class Runner:
        async def result(self):
            return "Native report"

    class Workflow:
        @asynccontextmanager
        async def run(self, message):
            events.append(("input", json.loads(message)))
            try:
                yield Runner()
            finally:
                events.append("runner-closed")

    class Builder:
        def build(self, entry_function=None):
            if entry_function is not None:
                raise KeyError(entry_function)
            events.append("default-workflow")
            return Workflow()

        @classmethod
        @asynccontextmanager
        async def from_config(cls, config):
            try:
                yield cls()
            finally:
                events.append("builder-closed")

    modules = {
        "aiq.builder.workflow_builder": {"WorkflowBuilder": Builder},
        "aiq.data_models.config": {"AIQConfig": SimpleNamespace(parse_obj=lambda value: value)},
        "aiq.front_ends.fastapi.register": {"register_fastapi_front_end": object()},
        "aiq.llm": {"register": object()},
        "aiq.llm.openai_llm": {"openai_llm": object()},
        "aiq_aira": {"register": object()},
        "aiq_aira.functions": {
            "artifact_qa": object(), "generate_queries": object(), "generate_summary": object()
        },
    }
    for name, attributes in modules.items():
        fake = ModuleType(name)
        fake.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, fake)
    module = _binding()
    monkeypatch.setattr(module, "_install_secret_filter", lambda: None)
    monkeypatch.setattr(module, "_native_config", lambda: {"workflow": {"_type": "ai_researcher"}})
    result = asyncio.run(module.create_graph().ainvoke("CF therapies", context=_context()))
    assert result == {"report": "Native report"}
    assert events[0] == "default-workflow"
    assert events[1][1]["topic"] == "CF therapies"
    assert events[-2:] == ["runner-closed", "builder-closed"]

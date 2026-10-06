"""Issue #214: bamboo-moon/zhisaotong-Agent onboarding contract.

Offline contracts only: no Docker, no network, no model call. Passing these does not
certify the Agent; certification is what promotes an ``adapting`` integration.

The tracked unit is ASCII-only. The upstream checkout lives in ``agent/``, which
``.gitignore`` excludes ("Runtime source/install materialization"): ABB restores it
from the ``[source]`` repository and revision in ``agent.toml`` before an evaluation
opens. The two contracts that read that checkout are skipped until it is materialized,
so this file passes both in a fresh clone and on a machine that has run a build.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agentbench.harness.registry import load_registry
from agentbench.runtime.agentcontainer.config import tomllib


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources" / "agents" / "50-zhisaotong-agent"
SNAPSHOT = UNIT / "agent"
REPOSITORY = "https://github.com/bamboo-moon/zhisaotong-Agent"
REVISION = "92569e61ac22ef4d902953a7d916e941921ab92f"

# The seven tools the upstream Agent exposes, and the six documents it ships.
TOOLS = (
    "rag_summarize",
    "get_weather",
    "get_user_location",
    "get_user_id",
    "get_current_month",
    "fetch_external_data",
    "fill_context_for_report",
)
DOCUMENT_COUNT = 6

# The Agent's production language is Chinese, so the input and answer contracts are
# exercised with the real Chinese payloads rather than Latin placeholders. They are
# spelled as \u escapes so this file stays ASCII, as the unit is required to be.
Q_FILTER = "\u626b\u5730\u673a\u5668\u4eba\u7684\u6ee4\u7f51\u591a\u4e45\u9700\u8981\u66f4\u6362\u4e00\u6b21\uff1f"
Q_MAINTENANCE = "\u7ef4\u62a4\u4fdd\u517b\u8981\u6ce8\u610f\u4ec0\u4e48\uff1f"
A_GREETING = "\u4f60\u597d"
A_FILTER_PADDED = "  \u6ee4\u7f51\u5efa\u8bae\u6bcf\u4e2a\u6708\u6e05\u6d17\u4e00\u6b21\u3002  "
A_FILTER = "\u6ee4\u7f51\u5efa\u8bae\u6bcf\u4e2a\u6708\u6e05\u6d17\u4e00\u6b21\u3002"
A_ERROR_HEAD = "\u6545\u969c\u4ee3\u7801 "
A_ERROR_TAIL = "E3 \u8868\u793a"
A_ERROR_JOINED = "\u6545\u969c\u4ee3\u7801 E3 \u8868\u793a"
A_NO_ANSWER = "\u6ca1\u6709\u56de\u7b54"

# Reading the checkout needs it on disk; a fresh clone does not have it.
needs_snapshot = pytest.mark.skipif(
    not (SNAPSHOT / "requirements.txt").is_file(),
    reason="agent/ is materialized from [source] at prepare time and is not tracked",
)


def _binding():
    spec = importlib.util.spec_from_file_location(
        "issue214_zhisaotong_binding", UNIT / "bindings" / "bridge.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _manifest():
    return tomllib.loads((UNIT / "agent.toml").read_text())


# ------------------------------------------------------------------- tracked unit


def test_tracked_unit_is_ascii_only():
    """The unit is published as ASCII source.

    The upstream checkout keeps its own language, but nothing this unit adds may
    depend on a non-ASCII environment. The excluded ``agent/`` tree is the restored
    upstream source, not part of this unit's tracked contribution.
    """
    offenders = []
    for path in sorted(UNIT.rglob("*")):
        if not path.is_file() or SNAPSHOT in path.parents:
            continue
        for number, line in enumerate(path.read_bytes().splitlines(), 1):
            if any(byte > 0x7F for byte in line):
                offenders.append(f"{path.relative_to(UNIT)}:{number}")

    assert offenders == [], "non-ASCII tracked content: " + ", ".join(offenders)


# --------------------------------------------------------------------------- input


def test_plain_case_input_is_accepted_as_text_or_message_mapping():
    module = _binding()
    graph = module.create_graph()
    try:
        assert graph._question(Q_FILTER) == Q_FILTER
        assert graph._question({"message": Q_MAINTENANCE}) == Q_MAINTENANCE
    finally:
        graph.close()


@pytest.mark.parametrize(
    "value,match",
    [
        ("", "non-empty"),
        ("   \n ", "non-empty"),
        (None, "non-empty"),
        (5, "non-empty"),
        ([], "non-empty"),
        ({}, "exactly"),
        ({"message": "question", "pdf": "/some/file"}, "exactly"),
        ({"messages": ["synthetic history"]}, "exactly"),
        ({"message": ""}, "non-empty"),
    ],
)
def test_unsupported_input_is_rejected_before_native_execution(value, match):
    graph = _binding().create_graph()
    try:
        with pytest.raises(ValueError, match=match):
            graph._question(value)
    finally:
        graph.close()


# -------------------------------------------------------------------------- output


def test_final_answer_text_reports_the_newest_assistant_turn():
    module = _binding()
    state = {"messages": [HumanMessage(A_GREETING), AIMessage(A_FILTER_PADDED)]}

    assert module._final_answer_text(state) == A_FILTER


def test_final_answer_text_joins_multipart_content():
    module = _binding()
    parts = [{"type": "text", "text": A_ERROR_HEAD}, {"type": "text", "text": A_ERROR_TAIL}]
    state = {"messages": [AIMessage(parts)]}

    assert module._final_answer_text(state) == A_ERROR_JOINED


@pytest.mark.parametrize(
    "state,match",
    [
        ({}, "no messages"),
        ({"messages": []}, "no messages"),
        ({"messages": "not a message list"}, "no messages"),
        ({"messages": [HumanMessage(A_NO_ANSWER)]}, "without a final assistant response"),
        ({"messages": ("not", "a", "message")}, "without a final assistant response"),
        # A turn that stopped on a tool call has no answer to report.
        ({"messages": [AIMessage("", tool_calls=[{"name": "rag_summarize", "args": {},
                                                  "id": "call-1"}])]},
         "without a final assistant response"),
        ({"messages": [AIMessage("   ")]}, "empty final response"),
        ({"messages": [AIMessage("")]}, "empty final response"),
    ],
)
def test_non_answers_are_failures_not_successful_empty_responses(state, match):
    """An unusable native turn must not be converted into a passing empty answer."""
    with pytest.raises(RuntimeError, match=match):
        _binding()._final_answer_text(state)


# ---------------------------------------------------------- model boundary contract


def test_model_clients_are_replaced_by_the_intercepted_openai_clients(monkeypatch):
    module = _binding()
    seen = {}

    class ChatOpenAI:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    class LocalEmbeddings:
        def __init__(self, model_name):
            seen["embedding_model"] = model_name

    openai = ModuleType("langchain_openai")
    openai.ChatOpenAI = ChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", openai)
    monkeypatch.setitem(sys.modules, "model", ModuleType("model"))
    monkeypatch.setattr(module, "_LocalEmbeddings", LocalEmbeddings)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-fixture-not-a-provider-key")

    module._install_model_clients()

    factory = sys.modules["model.factory"]
    assert isinstance(factory.chat_model, ChatOpenAI)
    assert isinstance(factory.embed_model, LocalEmbeddings)
    # The Agent's whole model boundary is the one route agent.toml declares, so the
    # client has to speak to that host and carry the intercepted credential.
    assert seen["base_url"] == "https://api.openai.com/v1"
    assert seen["base_url"] == module.INTERCEPTED_BASE_URL
    assert seen["api_key"] == "offline-fixture-not-a-provider-key"
    assert seen["embedding_model"] == module.RAG_EMBEDDING_MODEL
    assert sys.modules["model"].factory is factory


def test_missing_intercepted_credential_fails_before_any_model_call(monkeypatch):
    module = _binding()
    openai = ModuleType("langchain_openai")
    openai.ChatOpenAI = object
    monkeypatch.setitem(sys.modules, "langchain_openai", openai)
    monkeypatch.setitem(sys.modules, "model", ModuleType("model"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        module._install_model_clients()


# -------------------------------------------------------- knowledge base contract


def test_knowledge_index_is_rebuilt_into_the_binding_workspace(monkeypatch):
    """Upstream's committed index is empty, so the binding builds its own."""
    module = _binding()
    calls = []
    chroma_conf = {
        "collection_name": "agent",
        "persist_directory": "chroma_db",
        "md5_hex_store": "md5.text",
        "data_path": "data",
    }

    config_handler = ModuleType("utils.config_handler")
    config_handler.chroma_conf = chroma_conf
    utils = ModuleType("utils")
    utils.config_handler = config_handler

    class VectorStoreService:
        def load_document(self):
            calls.append(dict(config_handler.chroma_conf))

    vector_store = ModuleType("rag.vector_store")
    vector_store.VectorStoreService = VectorStoreService

    monkeypatch.setitem(sys.modules, "utils", utils)
    monkeypatch.setitem(sys.modules, "utils.config_handler", config_handler)
    monkeypatch.setitem(sys.modules, "rag.vector_store", vector_store)

    with TemporaryDirectory() as workspace:
        module._build_knowledge_index(Path(workspace))

    assert len(calls) == 1
    assert calls[0]["persist_directory"] == str(Path(workspace) / "chroma_db")
    # A fresh ledger, otherwise the six recorded hashes suppress every document.
    assert calls[0]["md5_hex_store"] == str(Path(workspace) / "md5.text")
    assert calls[0]["persist_directory"] != "chroma_db"
    assert calls[0]["md5_hex_store"] != "md5.text"


@needs_snapshot
def test_vendored_index_holds_the_collection_but_no_embeddings():
    """The recorded defect the rebuild exists to work around."""
    index = SNAPSHOT / "chroma_db" / "chroma.sqlite3"

    assert index.is_file()
    with sqlite3.connect(f"file:{index}?mode=ro", uri=True) as connection:
        collections = connection.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
        embeddings = connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

    assert collections == 1, "the upstream index should already declare the collection"
    assert embeddings == 0, "the upstream index is committed without embeddings"

    hashes = [line for line in (SNAPSHOT / "md5.text").read_text().split() if line.strip()]
    assert len(hashes) == DOCUMENT_COUNT, "every shipped document is already recorded as indexed"


# ------------------------------------------------------------------- resource life


def test_close_is_idempotent_and_releases_the_workspace():
    graph = _binding().create_graph()
    workspace = TemporaryDirectory(prefix="issue214-")
    graph._workspace = workspace
    released = Path(workspace.name)

    graph.close()
    graph.close()

    assert not released.exists()
    assert graph._workspace is None
    assert graph._agent is None


def test_failed_load_releases_the_workspace_it_already_created(monkeypatch):
    module = _binding()
    graph = module.create_graph()

    def failing_install():
        raise RuntimeError("model clients unavailable")

    monkeypatch.setattr(module, "_install_model_clients", failing_install)
    monkeypatch.setattr(module, "_prepend_source_root", lambda: None)

    with pytest.raises(RuntimeError, match="model clients unavailable"):
        graph._load()

    assert graph._workspace is None
    assert graph._agent is None


# --------------------------------------------------------- onboarding declarations


def test_unit_source_and_registry_are_pinned_to_issue214_revision():
    manifest = _manifest()
    source = json.loads((UNIT / "source-manifest.json").read_text())
    registration = load_registry(ROOT / "resources" / "registry.toml").find(
        "zhisaotong-agent", enabled_only=False
    )

    assert manifest["source"]["repository"] == REPOSITORY
    assert manifest["source"]["revision"] == REVISION
    assert source["revision"] == manifest["source"]["revision"]
    assert source["repository"] == manifest["source"]["repository"]
    assert registration.path == UNIT
    assert registration.status == "adapting"
    # A newly onboarded integration is registered but not selected.
    assert registration.enabled is False


def test_binding_declares_the_intercepted_route_and_no_tool_egress():
    manifest = _manifest()
    adapter = manifest["adapter"]
    interception = manifest["llm_interception"]

    assert adapter["type"] == "langgraph"
    assert adapter["binding"] == "bridge.py:create_graph"
    assert adapter["output_key"] == "answer"
    assert interception["credentials"][0]["agent_env"] == "OPENAI_API_KEY"
    assert len(interception["routes"]) == 1
    route = interception["routes"][0]
    assert route["host_patterns"] == ["api.openai.com"]
    assert route["path_patterns"] == ["/v1/chat/completions"]
    # get_weather / get_user_location need an Amap key this deployment withholds, and
    # upstream turns that failure into the error string the model already handles, so
    # no tool route is declared for them.
    assert not interception.get("tool_routes")


@needs_snapshot
def test_restored_checkout_is_faithful_and_safe_to_publish():
    manifest = _manifest()

    assert manifest["source"]["revision"] == REVISION
    documents = sorted(p.name for p in (SNAPSHOT / "data").glob("*") if p.is_file())
    assert len(documents) == DOCUMENT_COUNT
    assert sum(name.endswith(".pdf") for name in documents) == 1
    assert sum(name.endswith(".txt") for name in documents) == DOCUMENT_COUNT - 1
    assert (SNAPSHOT / "data" / "external" / "records.csv").is_file()
    assert (SNAPSHOT / "config" / "chroma.yml").is_file()

    # The seven tools are declared by the upstream prompt, and the binding must not
    # have grown an eighth one.
    prompt = (SNAPSHOT / "prompts" / "main_prompt.txt").read_text()
    for tool in TOOLS:
        assert tool in prompt, f"{tool} should still be reachable in this deployment"

    assert not any(path.name == ".env" for path in UNIT.rglob("*"))
    assert not any(path.name == ".git" for path in UNIT.rglob("*"))
    assert not any(path.is_symlink() for path in UNIT.rglob("*"))
    assert not (UNIT / "evaluation" / "input-contract.json").exists()


def test_unit_ships_every_tracked_file_the_build_reads():
    for name in ("README.md", "requirement.md", "Dockerfile", ".dockerignore",
                 "agent.toml", "source-manifest.json", "bindings/bridge.py"):
        assert (UNIT / name).is_file(), name
    assert (UNIT / "ground_truth").is_dir()
    # The upstream checkout is restored, never committed.
    assert "/resources/agents/*/agent/" in (ROOT / ".gitignore").read_text()


def test_requirement_profile_passes_the_official_kuma_parse():
    """KUMA's own parser reads requirement.md; a substring check of our own text would
    pass no matter what the profile meant."""
    from agentbench.sdk.plugin.kuma.onboarding import validate
    from kuma.repository.agent_profiles import parse_agent_profile

    validate(UNIT)

    profile = parse_agent_profile(UNIT / "requirement.md")
    assert profile.input_type == "text"
    assert (profile.strategy_group.id, profile.strategy_group.version) == (
        "basic-safety-general",
        "1",
    )
    assert set(profile.sections) >= {
        "production_scenario",
        "behaviors_to_test",
        "prohibited_behaviors",
    }
    assert 0 < len(profile.agent_description) <= 2000

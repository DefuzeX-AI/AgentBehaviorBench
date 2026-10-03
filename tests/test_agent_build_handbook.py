"""The maintained handbook reaches generation/review and invalidates stale plans."""
import pytest

from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.frameworks.langgraph import handbook
from tests.agent_build_fixtures import source, plan, Client, FILES, build
from tests.test_agent_build_acp import ACPClient, acp_plan


def test_langgraph_generation_and_review_receive_full_canonical_handbook(source, plan):
    expected = handbook.reference_documents()
    assert "# Writing LangGraph bindings" in expected[handbook.DOCUMENT_NAME]
    client = Client(plan)
    assert build(source, plan, client=client).status == "generated"
    assert client.requests[0]["framework_documents"] == {}
    for request in [*client.requests[1:], *client.reviews]:
        assert request["framework_documents"] == expected


def test_acp_requests_do_not_receive_langgraph_handbook(source, plan):
    selected = acp_plan(plan)
    files = {**FILES, "Dockerfile": FILES["Dockerfile"].replace("COPY bindings/ ./bindings/\n", "")}
    client = ACPClient(selected, files=files)
    assert build(source, selected, client=client).status == "generated"
    assert all(request["framework_documents"] == {} for request in [*client.requests, *client.reviews])


def test_handbook_change_replans_and_reviews_without_overwriting_files(source, plan, tmp_path, monkeypatch):
    checkout = tmp_path / "abb"
    guide = checkout / handbook.DOCUMENT_NAME
    guide.parent.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("", encoding="utf-8")
    guide.write_text("# Binding guide\nPreserve 原生行为.\n", encoding="utf-8")
    monkeypatch.setattr(handbook, "SOURCE_ROOT", checkout)
    assert build(source, plan).status == "generated"
    original = {name: (source.directory / name).read_bytes() for name in FILES}
    cached = Client(plan)
    assert build(source, plan, client=cached).status == "generated"
    assert cached.requests == cached.reviews == []
    guide.write_text(guide.read_text(encoding="utf-8") + "Release owned resources.\n", encoding="utf-8")
    changed = Client(plan)
    assert build(source, plan, client=changed).status == "generated"
    assert [request.get("target_path") for request in changed.requests] == [None]
    assert {request["target_path"] for request in changed.reviews} == set(FILES) - {".dockerignore"}
    assert all("Release owned resources." in request["framework_documents"][handbook.DOCUMENT_NAME]
               for request in changed.reviews)
    assert original == {name: (source.directory / name).read_bytes() for name in FILES}


def test_installed_package_uses_bundled_guide_not_working_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(handbook, "SOURCE_ROOT", tmp_path / "site-packages")
    bundle = tmp_path / "handbook.md"
    bundle.write_text("Installed guide: UTF-8 中文", encoding="utf-8")
    monkeypatch.setattr(handbook, "BUNDLED_DOCUMENT", bundle)
    unrelated = tmp_path / "docs"
    unrelated.mkdir()
    (unrelated / "LangGraph Bindings.md").write_text("Unrelated agent instructions", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert handbook.reference_documents() == {handbook.DOCUMENT_NAME: "Installed guide: UTF-8 中文"}


def test_missing_guide_fails_before_any_model_request(source, plan, tmp_path, monkeypatch):
    monkeypatch.setattr(handbook, "SOURCE_ROOT", tmp_path)
    monkeypatch.setattr(handbook, "BUNDLED_DOCUMENT", tmp_path / "missing.md")
    client = Client(plan)
    with pytest.raises(BuildError, match="Cannot read.*handbook"):
        build(source, plan, client=client)
    assert client.requests == client.reviews == []

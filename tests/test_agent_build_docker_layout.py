"""Source-relative model paths must be mapped to the actual outer build context."""
from types import SimpleNamespace
import pytest
from tests.agent_build_fixtures import source, plan, Client, FILES, build, write
from agentbench.onboarding.build_agent_env.build_dockerfile.service import steps
from agentbench.onboarding.build_agent_env.build_dockerfile.copy_sources import validate_copy_sources
from agentbench.onboarding.build_agent_env.common.errors import BuildError


def test_reported_upstream_paths_are_rendered_in_outer_context(source, plan):
    write(source.directory, "agent/ui/package.json", "{}")
    write(source.directory, "agent/requirements.txt", "")
    write(source.directory, "agent/backend/graph.py", "")
    files = {**FILES, "Dockerfile": '''FROM node:20-slim AS frontend
COPY ui/ /app/ui/
FROM python:3.11-slim
COPY requirements.txt /opt/agent/requirements.txt
COPY backend/ /opt/agent/agent/backend/
COPY agent/ /opt/agent/agent/
COPY --from=frontend /app/ui/dist/ /opt/agent/ui/dist/
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml /opt/agent/agent.toml
COPY bindings/ /opt/agent/bindings/
USER agent
'''}
    result = build(source, plan, client=Client(plan, files=files))
    assert result.status == "generated"
    text = (source.directory / "Dockerfile").read_text()
    assert '"agent/ui/"' in text
    assert '"agent/requirements.txt"' in text
    assert '"agent/backend/"' in text
    assert "COPY --from=frontend /app/ui/dist/ /opt/agent/ui/dist/" in text
    assert "COPY agent/ /opt/agent/agent/" in text


def test_docker_requests_include_both_path_namespaces(source, plan):
    client = Client(plan)
    build(source, plan, client=client)
    request = next(item for item in client.requests if item.get("target_path") == "Dockerfile")
    layout = request["build_context"]
    assert layout["source_root"] == "agent/"
    assert layout["evidence_path_base"] == "agent/"
    assert "agent/" in layout["outer_entries"]
    assert layout["injected_at_build"] == [".abb-runtime/"]
    assert next(f for f in request["context"]["files"] if f["path"] == "langgraph.json")["build_context_path"] == "agent/langgraph.json"


def test_validation_lists_every_missing_source_and_real_alternatives(source):
    write(source.directory, "agent/ui/package.json", "{}")
    write(source.directory, "agent/requirements.txt", "")
    with pytest.raises(BuildError) as error:
        validate_copy_sources("COPY ui/ /ui/\nCOPY requirements.txt /req.txt\n", source.directory)
    assert "agent/ui/" in str(error.value) and "agent/requirements.txt" in str(error.value)


def test_json_copy_with_flags_is_not_misparsed(source, plan):
    write(source.directory, "agent/requirements.txt", "")
    step = steps()[0]
    text = step.render({"content": 'FROM python:3.11\nCOPY --chown=10001:10001 ["requirements.txt", "/tmp/req.txt"]\nUSER agent\n'},
                       SimpleNamespace(source=source, completed={}))
    validate_copy_sources(text, source.directory)
    assert 'COPY --chown=10001:10001 ["agent/requirements.txt", "/tmp/req.txt"]' in text


def test_existing_outer_file_is_not_redirected(source):
    write(source.directory, "requirements.txt", "outer")
    write(source.directory, "agent/requirements.txt", "upstream")
    content = "COPY requirements.txt /tmp/req.txt\n"
    assert steps()[0].render({"content": content}, SimpleNamespace(source=source)) == content


@pytest.mark.parametrize("path", ["../outside", "/private/outside", "agent/../outside"])
def test_normalization_never_repairs_escaping_paths(source, path):
    with pytest.raises(BuildError, match="inside"):
        steps()[0].render({"content": f"COPY {path} /tmp/file\n"}, SimpleNamespace(source=source))


def test_source_symlink_is_not_treated_as_a_valid_prefix_repair(source, tmp_path):
    target = write(tmp_path, "outside.txt", "private")
    (source.directory / "agent/linked.txt").symlink_to(target)
    content = steps()[0].render({"content": "COPY linked.txt /tmp/file\n"}, SimpleNamespace(source=source))
    with pytest.raises(BuildError, match="linked.txt"):
        validate_copy_sources(content, source.directory)


def test_multiple_and_multiline_copy_sources_keep_container_destination(source):
    write(source.directory, "agent/requirements.txt", "")
    write(source.directory, "agent/constraints.txt", "")
    content = "COPY requirements.txt \\\n constraints.txt /tmp/deps/\n"
    text = steps()[0].render({"content": content}, SimpleNamespace(source=source))
    assert text == 'COPY ["agent/requirements.txt", "agent/constraints.txt", "/tmp/deps/"]\n'

"""A configuration review sees one file and must be told whose fields are whose.

`agent.toml` is assembled by the build program from validated plan facts and
deployment options, then handed to the reviewer as `proposed_content`. Without a
statement of which paths the program wrote, the reviewer asks for source evidence
that cannot exist for them and for artifacts (Dockerfile, requirement.md) that a
later step has not produced yet, and the build stops at step 01 of 5.

The same review must be able to say no. `status=complete` with a summary that
refuses the file used to pass the gate, which converted a review problem into a
`needs_input` reported against the next step.
"""
import pytest

from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.onboarding.build_agent_env.build_toml.rendering import PROGRAM_OWNED_FIELDS
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from tests.agent_build_fixtures import source, plan, Client, build

# Fields the model proposes. Checking them against repository source is the
# reason this review exists, so they must never be declared program-owned.
MODEL_AUTHORED = {"display_name", "framework", "adapter", "models", "tool_routes",
                  "runtime.env_keys", "runtime.secret_env_keys", "llm_interception",
                  "observe"}


class RecordingClient(Client):
    def __init__(self, plan, **kwargs):
        super().__init__(plan, **kwargs)
        self.prompts = []

    def generate(self, payload, *, prompt, schema):
        if payload.get("response_kind") == "configuration_review":
            self.prompts.append((payload["target_path"], prompt))
        return super().generate(payload, prompt=prompt, schema=schema)


def review_of(client, path):
    return next(review for review in client.reviews if review["target_path"] == path)


def prompt_of(client, path):
    return next(prompt for name, prompt in client.prompts if name == path)


def test_manifest_review_declares_the_paths_the_program_writes(source, plan):
    client = RecordingClient(plan)
    assert build(source, plan, client=client).status == 'generated'
    assert review_of(client, 'agent.toml')['program_owned_fields'] == list(PROGRAM_OWNED_FIELDS)


def test_every_declared_path_is_one_the_rendered_manifest_actually_holds(source, plan):
    client = RecordingClient(plan)
    build(source, plan, client=client)
    installed = tomllib.loads((source.directory / 'agent.toml').read_text(encoding='utf-8'))
    for path in review_of(client, 'agent.toml')['program_owned_fields']:
        node, *keys = path.split('.')
        assert node in installed, path
        node = installed[node]
        for key in keys:
            assert key in node, path
            node = node[key]


def test_model_authored_fields_stay_in_review_scope(source, plan):
    client = RecordingClient(plan)
    build(source, plan, client=client)
    declared = set(review_of(client, 'agent.toml')['program_owned_fields'])
    assert not declared & MODEL_AUTHORED


def test_only_the_manifest_step_declares_program_owned_fields(source, plan):
    client = RecordingClient(plan)
    build(source, plan, client=client)
    assert 'program_owned_fields' not in review_of(client, 'Dockerfile')
    assert 'program_owned_fields' not in review_of(client, 'requirement.md')


def test_review_prompt_names_the_declaration_and_the_unbuilt_files(source, plan):
    client = RecordingClient(plan)
    build(source, plan, client=client)
    prompt = prompt_of(client, 'agent.toml')
    assert 'program_owned_fields' in prompt
    assert 'completed_files' in prompt
    assert 'Dockerfile' in prompt and 'requirement.md' in prompt


def test_a_review_that_refuses_the_file_cannot_pass_the_gate(source, plan):
    verdict = ('The proposed agent.toml cannot be approved as written: the supplied '
               'evidence does not support the declared llm_interception routes.')

    class RefusingClient(Client):
        def generate(self, payload, *, prompt, schema):
            response = super().generate(payload, prompt=prompt, schema=schema)
            if payload.get('response_kind') == 'configuration_review':
                response['approved'] = False
                response['summary'] = verdict
            return response

    with pytest.raises(BuildError, match='cannot be approved as written'):
        build(source, plan, client=RefusingClient(plan))


def test_a_review_must_state_its_verdict(source, plan):
    class SilentClient(Client):
        def generate(self, payload, *, prompt, schema):
            response = super().generate(payload, prompt=prompt, schema=schema)
            if payload.get('response_kind') == 'configuration_review':
                response.pop('approved')
            return response

    with pytest.raises(BuildError, match='response schema'):
        build(source, plan, client=SilentClient(plan))

"""Durable Case artifacts, single-container mounts and original telemetry transport."""
import json
import os
from pathlib import Path

import pytest

from agentbench.sdk.integration.artifacts import FileArtifactStore
from agentbench.sdk.plugin.kuma.service import EvaluationPolicy


def test_case_is_durable_and_attempts_do_not_replace_history(tmp_path):
    store = FileArtifactStore(tmp_path / 'suite')
    case = store.case('agent', 0)
    case.publish_case(b'{"case":"one"}')
    first = case.attempt('first')
    first.write_json('steps/0001/result.json', {'status': 'failed'})
    second = case.attempt('second')
    second.write_json('steps/0001/result.json', {'status': 'succeeded'})
    reopened = FileArtifactStore(store.directory).case('agent', 0)
    assert (reopened.directory / 'case.json').read_bytes() == b'{"case":"one"}'
    assert json.loads((first.directory / 'steps/0001/result.json').read_text())['status'] == 'failed'
    with pytest.raises(ValueError, match='cannot be replaced'):
        case.publish_case(b'{"case":"other"}')


def test_artifact_paths_cannot_escape_or_follow_links(tmp_path):
    attempt = FileArtifactStore(tmp_path / 'suite').case('agent', 0).attempt('first')
    with pytest.raises(ValueError):
        attempt.write_json('../elsewhere.json', {})
    external = tmp_path / 'external'
    external.mkdir()
    (attempt.directory / 'link').symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError):
        attempt.write_json('link/secret.json', {})


def test_single_container_mounts_workspace_and_sdk_storage(tmp_path):
    repository = tmp_path / 'workspace'
    repository.mkdir()
    ledger = tmp_path / 'result/sdk/.kuma'
    ledger.mkdir(parents=True)
    arguments = EvaluationPolicy(ledger, repository=repository, target='/workspace',
                                 writable=True).run_arguments()
    workspace = [value for value in arguments if value.endswith('target=/workspace')]
    assert workspace == [f'type=bind,source={repository.resolve()},target=/workspace']
    assert any(str(ledger.parent) in value for value in arguments)
    assert not any('/run/abb-channel' in value for value in arguments)
    assert not (repository / '.kuma').exists()


def test_missing_external_storage_support_fails_before_sdk_call(tmp_path):
    from agentbench.sdk.plugin.kuma.integration import storage_options
    called = []
    def old_sdk(*, repo_path):
        called.append(repo_path)
    with pytest.raises(RuntimeError, match='storage_path'):
        storage_options(old_sdk, tmp_path)
    assert called == []


def test_slots_exist_before_generation_and_attempts_stay_under_case(tmp_path):
    from agentbench.sdk.integration.lifecycle import allocate_run
    store = FileArtifactStore(tmp_path / 'suite')
    generation = allocate_run(tmp_path / 'legacy', store, 'agent', {}, (0, 1))
    assert generation.is_dir()
    assert store.case('agent', 1).directory.is_dir()
    attempt = allocate_run(tmp_path / 'legacy', store, 'agent',
                           {'case_index': 0, 'attempt_id': 'attempt-one'})
    assert attempt == store.case('agent', 0).directory / 'attempts/attempt-one'


@pytest.mark.skipif(os.name == 'nt', reason='Controller transport runs in Linux')
def test_agent_response_cannot_follow_links_into_private_storage(tmp_path):
    from agentbench.sdk.integration.channel import collect_response
    source = tmp_path / 'response'
    source.mkdir()
    target = tmp_path / 'output'
    target.mkdir()
    private = tmp_path / 'private-case'
    private.write_text('future prompt')
    (source / 'result.json').symlink_to(private)
    with pytest.raises(OSError):
        collect_response(source, target)
    assert not (target / 'result.json').exists()


@pytest.mark.skipif(not hasattr(os, 'getuid') or getattr(os, 'getuid', lambda: -1)() != 0,
                    reason='Linux root-only ownership fixture')
def test_published_case_keeps_host_owner_for_future_attempts(tmp_path):
    import subprocess
    import sys
    from agentbench.runtime.docker.mount_permissions import _SCRIPT
    private = tmp_path / 'private'
    private.mkdir()
    (private / 'case.json').write_text('private')
    (private / 'case.json').chmod(0o600)
    shared = tmp_path / 'published'
    shared.mkdir()
    history = shared / 'old-case.json'
    history.write_text('immutable')
    os.chown(shared, 20002, 20002)
    os.chown(history, 20002, 20002)
    subprocess.run([sys.executable, '-I', '-S', '-c', _SCRIPT, 'agent',
                    '1', '20002', str(private), str(shared)], check=True)
    assert private.stat().st_uid == 10001
    assert (private / 'case.json').stat().st_uid == 10001
    assert shared.stat().st_uid == 20002
    assert shared.stat().st_gid == 10001
    assert shared.stat().st_mode & 0o777 == 0o770
    assert history.stat().st_uid == 20002 and history.read_text() == 'immutable'


def test_published_case_recovers_without_another_generation_request(tmp_path):
    from agentbench.sdk.common.artifacts import Artifacts
    from agentbench.sdk.plugin.kuma.generation import generate_collection
    from tests.test_case_preparation import generator
    calls = []
    create, options = generator(tmp_path / 'repo', calls=calls)
    publication = tmp_path / 'published'
    arguments = dict(count=1, options=options, repo=tmp_path / 'repo',
                     case_publications={'0': str(publication)})
    first = generate_collection(create, files=Artifacts(tmp_path / 'first'), **arguments)
    original = (publication / 'case.json').read_bytes()
    recovered = generate_collection(create, files=Artifacts(tmp_path / 'recovered'), **arguments)
    assert calls == [0]
    assert recovered['cases'] == first['cases']
    assert (publication / 'case.json').read_bytes() == original

    # A torn publication requires explicit repair; it must never silently bill
    # another Case or overwrite the original bytes.
    (publication / 'publication.json').unlink()
    with pytest.raises(ValueError, match='incomplete'):
        generate_collection(create, files=Artifacts(tmp_path / 'blocked'), **arguments)
    assert calls == [0]

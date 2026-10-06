import asyncio
import stat

import pytest

from agentbench.sdk.common.output_permissions import prepare_output, share_output
from agentbench.sdk.plugin.kuma import worker


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_host_prepares_judge_directory_for_atomic_report_handoff(tmp_path, monkeypatch):
    import os
    from agentbench.sdk.common.artifacts import Artifacts

    private = tmp_path / 'run'
    private.mkdir(mode=0o700)
    output = prepare_output(private / 'evaluation')
    judge = output / 'judge'
    owner = judge.stat().st_uid
    Artifacts(output).save('judge/context.json', {'history': 'original'})
    context = (judge / 'context.json').read_bytes()
    # Worker publication must not remove the host-owned directory permissions.
    with monkeypatch.context() as scoped:
        scoped.setattr(os, 'getuid', lambda: owner + 1)
        share_output(output)
    assert mode(private) == 0o700
    assert mode(output) == mode(judge) == 0o777
    assert judge.stat().st_uid == owner
    Artifacts(output).save('judge/report.json', {'status': 'issue'})
    Artifacts(output).save('judge/report.json', {'status': 'issue', 'received': True})
    assert (judge / 'context.json').read_bytes() == context


def test_output_is_readable_without_changing_content_or_private_parent(tmp_path):
    private = tmp_path / 'run'
    private.mkdir(mode=0o700)
    output = private / 'evaluation'
    output.mkdir()
    cases = output / 'cases'
    cases.mkdir(mode=0o700)
    manifest = output / 'manifest.json'
    manifest.write_bytes(b'{"phase":"batch_generated"}\n')
    manifest.chmod(0o600)
    case = cases / 'case.json'
    case.write_bytes(b'{}\n')
    case.chmod(0o600)
    share_output(output)
    assert mode(private) == 0o700
    assert mode(manifest) == mode(case) == 0o644
    assert mode(cases) == 0o755
    assert manifest.read_bytes() == b'{"phase":"batch_generated"}\n'


def test_output_does_not_follow_file_or_directory_symlinks(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir(mode=0o700)
    secret = outside / 'secret'
    secret.write_text('private')
    secret.chmod(0o600)
    output = tmp_path / 'output'
    output.mkdir()
    (output / 'file').symlink_to(secret)
    (output / 'directory').symlink_to(outside, target_is_directory=True)
    share_output(output)
    assert mode(secret) == 0o600
    assert mode(outside) == 0o700
    share_output(output / 'directory')
    assert mode(secret) == 0o600


def test_does_not_chmod_another_users_output(tmp_path, monkeypatch):
    output = tmp_path / 'output'
    output.mkdir()
    artifact = output / 'manifest.json'
    artifact.write_text('{}')
    artifact.chmod(0o600)
    import os
    monkeypatch.setattr(os, 'getuid', lambda: artifact.stat().st_uid + 1)
    share_output(output)
    assert mode(artifact) == 0o600


def test_startup_error_is_readable(tmp_path, monkeypatch):
    output = tmp_path / 'output'
    monkeypatch.setattr('sys.argv', ['worker', '--output', str(output),
                                   '--settings', str(tmp_path / 'missing.json')])
    assert worker.main() == 1
    assert mode(output / 'error.json') == 0o644


@pytest.mark.parametrize('failure', [False, True])
def test_worker_publishes_atomic_outputs_even_on_failure(tmp_path, monkeypatch, failure):
    output = tmp_path / 'output'

    async def fake_execute(*args, **kwargs):
        worker.Artifacts(output).save('manifest.json', {'phase': 'test'})
        assert mode(output / 'manifest.json') == 0o600
        if failure:
            raise RuntimeError('synthetic failure')
        return 0

    monkeypatch.setattr(worker, '_execute', fake_execute)
    if failure:
        with pytest.raises(RuntimeError, match='synthetic failure'):
            asyncio.run(worker.execute(tmp_path, output))
    else:
        assert asyncio.run(worker.execute(tmp_path, output)) == 0
    assert mode(output / 'manifest.json') == 0o644
    assert mode(output / 'timing.jsonl') & 0o044 == 0o044

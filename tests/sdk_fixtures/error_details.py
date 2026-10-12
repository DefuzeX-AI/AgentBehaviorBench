"""Real container, KUMA privacy rejection, and successful sibling Judge run."""
import asyncio
import json
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts, failure_message
from agentbench.sdk.plugin.kuma.runner import drive_run
from tests.sdk_fixtures.issue_run import sdk_run


def main(output):
    for name, answer in (('rejected', 'api_key=fixture-not-a-real-credential-123456789'),
                         ('accepted', 'Verified offline output')):
        root = output / name
        evaluation = root / 'evaluation'
        root.mkdir(parents=True, exist_ok=True)
        with sdk_run(root / 'repo', ['Echo current input']) as (run, provider):
            run.save_case(root / 'repo/case.json')
            shutil.copyfile(root / 'repo/case.json', root / 'case.json')
            async def invoke(payload, folder, evidence_provider):
                process = subprocess.run([sys.executable, '-c', 'import sys; print(sys.argv[1])', answer],
                                         text=True, capture_output=True, timeout=10, check=True)
                (folder / 'otel-status.json').write_text('{"status":"complete"}')
                return {'status': 'succeeded', 'output': process.stdout.strip()}
            summary = asyncio.run(drive_run(run, invoke, evaluation, provider=provider))
        artifacts = collect_artifacts(root, {'status': 'failed' if name == 'rejected' else 'succeeded'})
        Artifacts(root).save('run.json', {'sdk_version': version('kuma-defuzex'),
                                       'provider_mode': 'offline-custom', 'artifacts': artifacts})
        if name == 'rejected':
            error = artifacts['sdk_error']
            assert error['code'] == 'sensitive_data_blocked', error
            assert error['details']['reasons'], error
            assert error['input_id'] == 'input-0' and error['phase'] == 'submission'
            assert summary['submission'] == 'failed' and summary['judge'] == 'pending'
            print('Original SDK privacy rejection retained:', failure_message(artifacts), flush=True)
        else:
            assert summary['submission'] == 'committed' and summary['judge'] == 'received', summary
            report = json.loads((evaluation / 'judge/report.json').read_text())
            assert report['status'] == 'pass'
            print('Successful sibling: original output submitted and Judge received', flush=True)
    (output / 'acceptance.json').write_text(json.dumps({'status': 'passed', 'network': 'none',
        'sdk_version': version('kuma-defuzex'), 'original_sdk_privacy_policy': 'unchanged'}, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))

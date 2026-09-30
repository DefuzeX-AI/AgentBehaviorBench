"""Real container/SDK/Agent flow, with offline Case and Judge providers."""
import asyncio
import json
from pathlib import Path
import sys

import kuma
import tomllib
from kuma.providers.official_case import _safe_case_payload

from agentbench.sdk.plugin.kuma.worker import execute, main


output = Path('/run/abb-output')
repository = Path('/tmp/environment-sdk-repo')
repository.mkdir()
manifest = tomllib.loads(Path('/opt/agent/agent.toml').read_text())
has_workspace = bool(manifest.get('evaluation', {}).get('workspace'))
original_create = kuma.create_run


def cases(context):
    # Validate the very payload the official provider would send, without
    # making a paid request. The real SDK still creates and saves the Case.
    payload, _ = _safe_case_payload(context, allow_sensitive=False,
                                    evidence_capabilities=(), max_steps=1)
    scenario = payload['behavior_spec']['production_scenario']
    assert 'Runtime: docker' in scenario and 'worker UID: 10001' in scenario
    assert 'internal container network' in scenario
    assert 'python' in scenario
    if has_workspace:
        assert 'Task workspace: /home/agent/workspace; initial state: empty' in scenario
        assert 'initialized afresh for each Case' in scenario
    else:
        assert 'No dedicated task workspace' in scenario
    (output / 'case-generation-request.json').write_text(json.dumps(payload, indent=2))
    return {'case_id': 'environment-acceptance', 'input_type': 'text', 'inputs': [
        {'input_id': 'one', 'payload_type': 'text', 'payload': 'environment works'}]}


def judge(context):
    assert context.history[0].submission.output == 'environment works'
    return {'status': 'pass', 'summary': 'Offline environment integration acceptance', 'issues': []}


def offline_create(**options):
    if 'agent_profile_path' in options:
        assert options['agent_profile_path'] != Path('/opt/agent/requirement.md')
        return original_create(**options, case_provider=cases, judge_provider=judge)
    return original_create(**options, judge_provider=judge)


kuma.create_run = offline_create
sys.argv = ['environment-check', '--output', str(output / 'generation'), '--sdk-repo', str(repository)]
assert main() == 0, (output / 'generation/error.json').read_text()
collection = json.loads((output / 'generation/case-collection.json').read_text())
case = collection['cases'][0]
environment = json.loads(Path('/run/abb-input/execution-environment.json').read_text())
settings = {'mode': 'execute', 'case_artifact': case['artifact'],
            'expected_case': {'case_id': case['case_id'], 'content_sha256': case['content_sha256']},
            'execution_environment': environment}
code = asyncio.run(execute(Path('/opt/agent'), output / 'execution', settings, sdk_repo=repository))
assert code == 0, (output / 'execution/error.json').read_text()
assert json.loads((output / 'execution/inputs/0001/result.json').read_text())['output'] == 'environment works'
assert json.loads((output / 'execution/judge/report.json').read_text())['status'] == 'pass'
assert 'Execution environment supplied by ABB' not in Path('/opt/agent/requirement.md').read_text()
print('Environment facts reached the Case request; real Agent output and offline Judge passed.')

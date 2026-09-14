"""Verify the migrated adapter against the package installed by its real overlay."""

import importlib.metadata
import json
import os
from pathlib import Path

import agentbench
from agentbench.sdk import resolve_sdk
from agentbench.sdk.contracts import PreparedCase, SDKRunnerContext
from agentbench.sdk.plugin.kuma.generation import artifact_case
from agentbench.sdk.plugin.kuma.worker import execute

from container_run import main


assert callable(execute)
assert os.environ['ABB_ACCEPTANCE_NATIVE_SETTING'] == 'preserved'
selection = resolve_sdk('kuma')
runner = selection.value.create_benchmark_runner(
    context=SDKRunnerContext(environ={}, model=None, trace_sink=None, trace_max_bytes=1024),
    options={},
)
assert callable(runner.prepare_cases) and callable(runner.run_case)
assert not hasattr(runner, 'run') and not hasattr(runner, '_case_batches')
assert PreparedCase(0).case_index == 0
output = Path('/artifacts')
(output / 'package.json').write_text(json.dumps({
    'distribution': 'kuma-defuzex',
    'version': importlib.metadata.version('kuma-defuzex'),
    'adapter': selection.reference.object_ref,
    'runtime': agentbench.__file__,
    'runner_contract': ['prepare_cases', 'run_case'],
    'native_environment_setting': os.environ['ABB_ACCEPTANCE_NATIVE_SETTING'],
}, indent=2))
main()
case = artifact_case(json.loads((output / 'case.json').read_text()))
assert case['inputs'][0]['payload'] == 'directory adapter works'

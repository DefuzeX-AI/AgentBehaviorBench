"""Verify the migrated adapter against the package installed by its real overlay."""

import importlib.metadata
import json
from pathlib import Path

import agentbench
from agentbench.sdk import resolve_sdk
from agentbench.sdk.plugin.kuma.generation import artifact_case
from agentbench.sdk.plugin.kuma.worker import execute

from container_run import main


assert callable(execute)
selection = resolve_sdk('kuma')
output = Path('/artifacts')
(output / 'package.json').write_text(json.dumps({
    'distribution': 'kuma-defuzex',
    'version': importlib.metadata.version('kuma-defuzex'),
    'adapter': selection.reference.object_ref,
    'runtime': agentbench.__file__,
}, indent=2))
main()
case = artifact_case(json.loads((output / 'case.json').read_text()))
assert case['inputs'][0]['payload'] == 'directory adapter works'

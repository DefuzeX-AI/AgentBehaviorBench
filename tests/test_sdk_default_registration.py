import sys
from types import SimpleNamespace

import pytest

from agentbench.sdk.contracts import EvaluationSDKPlugin
from agentbench.sdk.integration.plugin import ContainerSDKPlugin
from agentbench.sdk.plugins import evaluation_plan, resolve_sdk
from agentbench.sdk.runtime import build_evaluation_runner
from tests.test_sdk_directory import adapter_directory, add_adapter


def test_declaration_is_discovered_without_loading_sdk_code(adapter_directory):
    directory = add_adapter(adapter_directory, name='minimal', source='''
from pathlib import Path
from agentbench.sdk.integration.plugin import ContainerSDKPlugin
plugin = ContainerSDKPlugin(create_run=__package__ + '.backend:create_run',
    requirements=Path(__file__).with_name('requirements.txt'))
''')
    (directory / 'requirements.txt').write_text('vendor-package==1.0\n')
    (directory / 'backend.py').write_text('raise AssertionError("SDK code imported on host")\n')
    selection = resolve_sdk('minimal')
    assert isinstance(selection.value, EvaluationSDKPlugin)
    runner = build_evaluation_runner(evaluation_plan(selection=selection),
        model=None, trace_sink=None, trace_max_bytes=1024, environ={})
    assert runner.validate_sdk(SimpleNamespace(path=directory)) == 'sdk-container'
    assert 'agentbench.sdk.plugin.minimal.backend' not in sys.modules


@pytest.mark.parametrize('reference', ['missing', 'module:', ':factory', 'module:object.method'])
def test_invalid_factory_reference_fails_without_import(tmp_path, reference):
    with pytest.raises(ValueError, match='module:function'):
        ContainerSDKPlugin(create_run=reference, requirements=tmp_path / 'requirements.txt')

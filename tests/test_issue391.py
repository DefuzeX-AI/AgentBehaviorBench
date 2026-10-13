"""The injected worker must publish Cases with only its bootstrap dependencies."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

import pytest
from packaging.requirements import Requirement

from agentbench.runtime.docker.worker_build import worker_build_context
from tests.test_issue85 import agent_config


PUBLICATION_SCRIPT = '''
import json
from pathlib import Path
import sys
sys.path[:0] = sys.argv[1:3]
from agentbench.sdk.integration import FileArtifactStore
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
store = FileArtifactStore(Path(sys.argv[3]))
case = store.case('example-agent', 0)
content = b'{"case_id":"example-case"}'
case.publish_case(content)
attempt = case.attempt('example-attempt')
attempt.write_json('steps/0001/result.json', {'status': 'succeeded'})
assert (case.directory / 'case.json').read_bytes() == content
assert json.loads((attempt.directory / 'steps/0001/result.json').read_text()) == {'status': 'succeeded'}
print('Case publication succeeded')
'''


@pytest.mark.parametrize('framework', ['langgraph', 'acp'])
def test_clean_worker_can_publish_case_with_declared_dependencies(tmp_path, framework):
    config = agent_config(tmp_path, framework=framework)
    dependencies = tmp_path / 'bootstrap'
    dependencies.mkdir()
    with worker_build_context(config) as (context, _):
        runtime = context / '.abb-runtime'
        requirements = runtime / 'agentbench/runtime/docker/requirements.txt'
        # Copy only declared, applicable packages; the subprocess cannot see the
        # host site-packages or an Agent's incidental dependencies.
        for line in requirements.read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            requirement = Requirement(line)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            spec = importlib.util.find_spec(requirement.name)
            assert spec is not None, f'Test environment lacks {requirement.name}'
            assert spec.submodule_search_locations
            shutil.copytree(next(iter(spec.submodule_search_locations)),
                            dependencies / requirement.name)

        output = tmp_path / 'published'
        result = subprocess.run(
            [sys.executable, '-I', '-S', '-c', PUBLICATION_SCRIPT,
             str(runtime), str(dependencies), str(output)],
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == 'Case publication succeeded'


@pytest.mark.skipif(not os.getenv('ABB_ISSUE391_DOCKER'), reason='Opt-in Docker build')
@pytest.mark.parametrize('version', ['3.10', '3.12'])
def test_clean_container_can_publish_case(tmp_path, version):
    config = agent_config(tmp_path, version=version)
    tag = f'abb-issue391:{uuid4().hex}'
    output = Path(__file__).parents[1] / 'results/verification/issue391' / version
    output.mkdir(parents=True, exist_ok=True)
    try:
        with worker_build_context(config) as (context, dockerfile):
            result = subprocess.run(
                ['docker', 'build', '-t', tag, '-f', str(dockerfile), str(context)],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
            (output / 'build.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            assert result.returncode == 0, f'See {output}/build.log'
        result = subprocess.run(
            ['docker', 'run', '--rm', '--network', 'none', tag, 'python', '-I',
             '-c', PUBLICATION_SCRIPT, '/opt/abb-runtime', '/opt/abb-runtime', '/tmp/published'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        (output / 'container.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        assert result.returncode == 0, f'See {output}/container.log'
        assert result.stdout.strip() == 'Case publication succeeded'
    finally:
        subprocess.run(['docker', 'image', 'rm', tag], capture_output=True, timeout=60)

"""Injected runtime dependencies must reach the Agent's Python interpreter."""
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from uuid import uuid4

import pytest
from packaging.requirements import Requirement

from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.runtime.docker.worker_build import worker_build_context


def agent_config(tmp_path, *, version='3.10', venv=False, framework='langgraph'):
    unit = tmp_path / 'unit'
    (unit / 'agent').mkdir(parents=True)
    (unit / 'agent.toml').write_text(
        f'framework = "{framework}"\n[adapter]\ntype = "{framework}"\n'
        'config = "langgraph.json"\ngraph_id = "test"\n')
    (unit / 'agent/langgraph.json').write_text('{"graphs":{"test":"main:graph"}}')
    environment = ('RUN python -m venv /opt/venv\nENV PATH=/opt/venv/bin:$PATH\n'
                   if venv else '')
    dockerfile = unit / 'Dockerfile'
    dockerfile.write_text(
        f'FROM python:{version}-slim\n{environment}'
        'RUN useradd --create-home agent\nWORKDIR /opt/agent\n'
        'COPY agent/ ./agent/\nCOPY agent.toml ./agent.toml\n'
        'COPY .abb-runtime/ /opt/abb-runtime/\n'
        'ENV PYTHONPATH=/opt/abb-runtime\nUSER agent\n')
    return SimpleNamespace(agent_root=unit, build_context=unit, dockerfile=dockerfile)


@pytest.mark.parametrize('framework', ['langgraph', 'acp'])
def test_worker_stages_conditional_tomli_without_modifying_agent(tmp_path, framework):
    config = agent_config(tmp_path, framework=framework)
    original = config.dockerfile.read_bytes()
    with worker_build_context(config) as (context, dockerfile):
        requirements = context / '.abb-runtime/agentbench/runtime/docker/requirements.txt'
        assert requirements.is_file(), 'Injected runtime dependencies are missing'
        entries = [Requirement(line) for line in requirements.read_text().splitlines()
                   if line and not line.startswith('#')]
        tomli = next(item for item in entries if item.name == 'tomli')
        assert tomli.marker.evaluate({'python_version': '3.10'})
        assert not tomli.marker.evaluate({'python_version': '3.11'})
        project = tomllib.loads((Path(__file__).parents[1] / 'pyproject.toml').read_text())
        assert str(tomli) in [str(Requirement(item)) for item in project['project']['dependencies']]
        source = dockerfile.read_text()
        assert '-r /opt/abb-runtime-deps/requirements.txt' in source
        assert 'python -m pip --isolated install' in source
        assert source.rstrip().endswith('USER agent')
    assert config.dockerfile.read_bytes() == original
    assert not (config.agent_root / '.abb-runtime').exists()


@pytest.mark.skipif(not os.getenv('ABB_ISSUE85_DOCKER'), reason='Opt-in Docker build')
@pytest.mark.parametrize('version,venv', [('3.10', False), ('3.10', True), ('3.11', False)])
def test_clean_image_loads_injected_langgraph_config(tmp_path, version, venv):
    config = agent_config(tmp_path, version=version, venv=venv)
    tag = f'abb-issue85:{uuid4().hex}'
    output = Path(__file__).parents[1] / 'results/verification/issue85' / f'{version}-venv-{venv}'
    output.mkdir(parents=True, exist_ok=True)
    try:
        with worker_build_context(config) as (context, dockerfile):
            build = subprocess.run(
                ['docker', 'build', '-t', tag, '-f', str(dockerfile), str(context)],
                capture_output=True, text=True, timeout=300)
            (output / 'build.log').write_text(build.stdout + build.stderr)
            assert build.returncode == 0, f'See {output}/build.log'
        # Execute the real parser from the injected sources without unrelated
        # Agent/framework dependencies masking this bootstrap failure.
        script = (
            'import importlib.util,json,os,runpy,sys; '
            'module=runpy.run_path("/opt/abb-runtime/agentbench/adapter/langgraph/config.py"); '
            'config=module["LangGraphAdapterConfig"].from_agent_dir("/opt/agent"); '
            'assert config.entrypoint == "main:graph"; '
            'assert os.getuid() != 0; '
            f'assert sys.executable == "{ "/opt/venv/bin/python" if venv else "/usr/local/bin/python" }"; '
            f'assert (importlib.util.find_spec("tomli") is not None) == {version == "3.10"}; '
            'print(json.dumps({"status":"passed","python":sys.version,"executable":sys.executable}))')
        result = subprocess.run(
            ['docker', 'run', '--rm', '--network', 'none', tag, 'python', '-c', script],
            capture_output=True, text=True, timeout=60)
        (output / 'container.log').write_text(result.stdout + result.stderr)
        assert result.returncode == 0, f'See {output}/container.log'
        (output / 'acceptance.json').write_text(json.dumps(json.loads(result.stdout), indent=2))
    finally:
        subprocess.run(['docker', 'image', 'rm', tag], capture_output=True, timeout=60)

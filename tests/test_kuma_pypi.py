"""KUMA package installation belongs to its plugin, not a local source checkout."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agentbench.cli.main import build_parser
from agentbench.harness.errors import ProviderSelectionError
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.docker.image_builder import DockerImageBuilder
from agentbench.runtime.docker.policy import DockerPolicy
from agentbench.runtime.docker.worker_build import worker_build_context
from agentbench.sdk import discover_sdks, resolve_sdk
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.sdk.plugin.kuma.image import evaluation_agent


@pytest.fixture
def echo_agent(tmp_path):
    root = tmp_path / 'echo-agent'
    (root / 'agent').mkdir(parents=True)
    (root / 'agent' / 'main.py').write_text('print("echo")\n')
    (root / 'evaluation').mkdir()
    (root / 'evaluation' / 'profile.md').write_text('Offline profile fixture\n')
    (root / 'evaluation' / 'input-contract.json').write_text('{"encoding":"identity"}')
    (root / 'agent.toml').write_text(
        'agent_id = "kuma-pypi-echo"\nframework = "fixture"\n'
        '[runtime]\ntype = "docker"\ntimeout_sec = 60\n'
        '[build]\ncontext = "."\ndockerfile = "Dockerfile"\n'
        '[launch]\nargv = ["python", "/opt/agent/agent/main.py"]\n')
    (root / 'Dockerfile').write_text('FROM python:3.11-slim\nUSER agent\n')
    return SimpleNamespace(path=root, agent_id='kuma-pypi-echo', framework='fixture')


def test_kuma_is_only_available_at_its_new_plugin_path():
    reference = resolve_sdk('kuma').reference
    assert reference.object_ref == 'agentbench.sdk.plugin.kuma.plugin:plugin'
    assert 'kuma' in {item.name for item in discover_sdks()}
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module('agentbench.sdk.kuma')


def test_overlay_installs_pypi_requirements_without_sdk_source(echo_agent):
    original_manifest = (echo_agent.path / 'agent.toml').read_bytes()
    original_dockerfile = (echo_agent.path / 'Dockerfile').read_bytes()
    with evaluation_agent(echo_agent) as staged:
        dockerfile = (staged.path / 'Dockerfile').read_text()
        assert '--index-url https://pypi.org/simple' in dockerfile
        assert 'python -m pip --isolated install' in dockerfile
        assert '-r /opt/abb-sdk/requirements.txt' in dockerfile
        assert dockerfile.rstrip().endswith('USER agent')
        requirements = staged.path / '.abb-sdk/requirements.txt'
        assert 'kuma-defuzex[otel]==' in requirements.read_text()
        assert {item.name for item in requirements.parent.iterdir()} == {'requirements.txt'}
        assert 'agentbench.sdk.plugin.kuma.worker' in (staged.path / 'agent.toml').read_text()
        assert not (staged.path / '.abb-sdk/src').exists()
        assert (staged.path / 'agent/.gitignore').read_text().strip() == '/.kuma/'
    assert (echo_agent.path / 'agent.toml').read_bytes() == original_manifest
    assert (echo_agent.path / 'Dockerfile').read_bytes() == original_dockerfile
    assert not (echo_agent.path / '.abb-sdk').exists()
    assert not (echo_agent.path / 'agent/.gitignore').exists()


def test_preflight_does_not_require_host_sdk_checkout_or_import(echo_agent, monkeypatch):
    import builtins
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == 'kuma' or name.startswith('kuma.'):
            pytest.fail('Host preflight must not import the container SDK')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'offline-not-used'})
    assert runner.validate_sdk(echo_agent) == 'official-container'
    assert not hasattr(runner, 'sdk')


def test_old_sdk_source_option_and_cli_flag_are_removed():
    with pytest.raises(ProviderSelectionError, match='sdk_source'):
        KumaContainerRunner(options={'sdk_source': '/old/checkout'})
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(['evaluate', '--sdk-source', '/old/checkout'])
    assert error.value.code == 2


@pytest.mark.skipif(not os.getenv('ABB_KUMA_PYPI_BASE_IMAGE'), reason='Opt-in real PyPI image build')
def test_real_pypi_overlay_and_offline_case_judge(echo_agent):
    """Build the actual overlay, then run the real PyPI SDK without network."""
    base = os.environ['ABB_KUMA_PYPI_BASE_IMAGE']
    # Use an existing image with Python and an unprivileged agent user. A fresh
    # runtime path prevents old code in that image from hiding migration errors.
    (echo_agent.path / 'Dockerfile').write_text(
        f'FROM {base}\nWORKDIR /opt/agent\n'
        'ENV PYTHONPATH=/opt/abb-current-runtime\n'
        'COPY .abb-runtime/ /opt/abb-current-runtime/\n'
        'COPY agent/ /opt/agent/agent/\n'
        'COPY agent.toml /opt/agent/agent.toml\nUSER agent\n')
    output = Path(__file__).resolve().parents[1] / 'results/verification' / f'kuma-pypi-{uuid4().hex}'
    output.mkdir(parents=True)
    with evaluation_agent(echo_agent) as staged:
        config = AgentContainerConfig.from_agent_dir(
            staged.path, secret_resolver=EnvironmentSecretResolver({}), environ={})
        assert config.argv[-1] == 'agentbench.sdk.plugin.kuma.worker'
        assert config.environment == {}
        (output / 'Dockerfile').write_text((staged.path / 'Dockerfile').read_text())
        requirements = (staged.path / '.abb-sdk/requirements.txt').read_text()
        (output / 'requirements.txt').write_text(requirements)
        with worker_build_context(config) as (context, dockerfile):
            assert (context / '.abb-runtime/agentbench/sdk/plugin/kuma/requirements.txt').is_file()
            assert not (context / '.abb-runtime/agentbench/sdk/kuma').exists()
            image = DockerImageBuilder().build(context=context, dockerfile=dockerfile,
                                              repository='kuma-pypi-acceptance')
    print(f'Built PyPI evaluation image: {image}', flush=True)
    fixtures = (Path(__file__).parent / 'sdk_fixtures').resolve()
    result = subprocess.run([
        'docker', 'run', '--rm', '--network', 'none', '--user', '10001:10001',
        *DockerPolicy().run_arguments(), '--env', 'PYTHONDONTWRITEBYTECODE=1',
        '--env', 'KUMA_API_KEY=', '--env', 'DEFUZEX_API_KEY=',
        '--mount', f'type=bind,source={fixtures},target=/checks,readonly',
        '--mount', f'type=bind,source={output},target=/artifacts',
        '--entrypoint', 'python', image, '/checks/pypi_check.py',
    ], capture_output=True, text=True, timeout=60)
    (output / 'container.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    assert result.returncode == 0, f'See {output / "container.log"}'
    package = json.loads((output / 'package.json').read_text())
    expected_version = next(line.split('==', 1)[1] for line in requirements.splitlines()
                            if line.startswith('kuma-defuzex'))
    assert package['version'] == expected_version
    assert package['adapter'] == 'agentbench.sdk.plugin.kuma.plugin:plugin'
    assert package['runtime'].startswith('/opt/abb-current-runtime/')
    run = json.loads((output / 'run.json').read_text())
    assert run['report']['status'] == 'pass'
    assert run['sdk_version'] == expected_version
    for name in ('case.json', 'agent-output.json', 'judge.json'):
        assert (output / name).is_file()
    (output / 'verification.json').write_text(json.dumps({
        'status': 'passed', 'image': image, 'package': package,
        'dependency_source': 'https://pypi.org/simple', 'execution_network': 'none',
        'providers': 'offline-custom', 'production_services_called': False,
    }, indent=2))
    print(f'PyPI acceptance artifacts retained: {output}', flush=True)

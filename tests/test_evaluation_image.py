"""Independent SDKs can stage controllers through the shared image helper."""

from types import SimpleNamespace

from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.runtime.docker.evaluation_image import evaluation_image


def make_unit(tmp_path):
    root = tmp_path / 'unit'
    (root / 'agent/ground_truth').mkdir(parents=True)
    (root / 'agent/ground_truth/native.txt').write_text('Native Agent data')
    (root / 'ground_truth').mkdir()
    (root / 'ground_truth/answer.json').write_text('Private evaluation answer')
    (root / '.env').write_text('PRIVATE_TOKEN=not-for-the-image')
    (root / 'evaluation/workspace/tasks').mkdir(parents=True)
    (root / 'evaluation/workspace/tasks/task.txt').write_text('Declared task fixture')
    (root / 'reports').mkdir()
    (root / 'reports/old-run.txt').write_text('Unrelated run output')
    (root / 'agent.toml').write_text(
        'agent_id = "independent"\nframework = "fixture"\n'
        '[runtime]\ntype = "docker"\nenv_keys = ["NATIVE_SETTING"]\n'
        '[launch]\nargv = ["python", "agent.py"]\n'
        '[evaluation.workspace]\npath = "/workspace"\n'
        'initial_state = "fixture"\nfixture = "evaluation/workspace"\n')
    (root / 'Dockerfile').write_text('FROM python:3.12-slim\nUSER 10001:10001\n')
    requirements = tmp_path / 'independent-requirements.txt'
    requirements.write_text('independent-sdk==1.2.3\n')
    return SimpleNamespace(path=root, agent_id='independent', framework='fixture'), requirements


def test_unrelated_sdk_only_supplies_dependencies_and_entrypoint(tmp_path):
    agent, requirements = make_unit(tmp_path)
    originals = {name: (agent.path / name).read_bytes() for name in ('agent.toml', 'Dockerfile')}
    with evaluation_image(agent, requirements=requirements, worker_module='independent_sdk.controller') as staged:
        manifest = tomllib.loads((staged.path / 'agent.toml').read_text())
        assert manifest['runtime']['env_keys'] == ['NATIVE_SETTING']
        assert 'worker_env_keys' not in manifest['runtime']
        argv = manifest['launch']['argv']
        assert argv[:3] == ['python', '-I', '-c']
        assert "sys.path.insert(0, '/opt/abb-sdk-runtime')" in argv[-1]
        assert "run_module('independent_sdk.controller'" in argv[-1]
        dockerfile = (staged.path / 'Dockerfile').read_text()
        assert 'KUMA' not in dockerfile
        assert 'requirement.md' not in dockerfile
        assert dockerfile.rstrip().endswith('USER 10001:10001')
        assert (staged.path / '.abb-sdk/requirements.txt').read_bytes() == requirements.read_bytes()
        assert not (staged.path / 'ground_truth').exists()
        assert not (staged.path / '.env').exists()
        assert not (staged.path / 'reports').exists()
        assert (staged.path / 'agent/ground_truth/native.txt').read_text() == 'Native Agent data'
        assert (staged.path / 'evaluation/workspace/tasks/task.txt').read_text() == 'Declared task fixture'
    assert not staged.path.exists()
    for name, content in originals.items():
        assert (agent.path / name).read_bytes() == content


def test_historical_recipe_receives_controller_overlay(tmp_path):
    agent, requirements = make_unit(tmp_path)
    (agent.path / 'historical').mkdir()
    (agent.path / 'historical/Dockerfile').write_text('FROM python:3.13\nUSER 10001\n')
    path = agent.path / 'agent.toml'
    path.write_text(path.read_text().replace('path = "/workspace"', 'path = "/workspace/task"')
                    + '\n[build]\ncontext="."\ndockerfile="historical/Dockerfile"\n')
    with evaluation_image(agent, requirements=requirements, worker_module='example.worker') as staged:
        selected = (staged.path / 'historical/Dockerfile').read_text()
        assert 'FROM python:3.13' in selected
        assert 'COPY .abb-sdk/' in selected
        assert 'COPY .abb-sdk/' not in (staged.path / 'Dockerfile').read_text()


def test_controller_settings_and_documents_belong_to_the_calling_sdk(tmp_path):
    agent, requirements = make_unit(tmp_path)
    (agent.path / 'sdk-profile.txt').write_text('Independent SDK profile')
    seen = []

    def configure(source):
        seen.append(tomllib.loads(source))
        return source + '\n[independent_sdk]\nmode = "offline"\n'

    with evaluation_image(
        agent, requirements=requirements, worker_module='independent_sdk.controller',
        worker_environment=('INDEPENDENT_TOKEN',), manifest_transform=configure,
        image_environment=('INDEPENDENT_OFFLINE=1',), required_files=('sdk-profile.txt',),
        optional_files=('evaluation', 'absent.json'), install_command='',
    ) as staged:
        manifest = tomllib.loads((staged.path / 'agent.toml').read_text())
        assert manifest['runtime']['env_keys'] == ['NATIVE_SETTING']
        assert manifest['runtime']['worker_env_keys'] == ['INDEPENDENT_TOKEN']
        assert seen[0]['runtime']['worker_env_keys'] == ['INDEPENDENT_TOKEN']
        assert manifest['independent_sdk']['mode'] == 'offline'
        dockerfile = (staged.path / 'Dockerfile').read_text()
        assert 'ENV INDEPENDENT_OFFLINE=1' in dockerfile
        assert 'COPY sdk-profile.txt /opt/agent/sdk-profile.txt' in dockerfile
        assert 'COPY evaluation/ /opt/agent/evaluation/' in dockerfile
        assert 'absent.json' not in dockerfile
        assert 'pip --isolated install' not in dockerfile


def test_kuma_wrapper_keeps_install_and_whitelist_overrides(tmp_path, monkeypatch):
    from agentbench.sdk.plugin.kuma import image

    agent, _ = make_unit(tmp_path)
    calls = []
    monkeypatch.setattr(image, 'SDK_INSTALL', '')

    def whitelist(source, path, routes):
        calls.append((path, routes))
        return source

    monkeypatch.setattr(image, 'append_whitelist', whitelist)
    with image.evaluation_agent(agent, backend='https://sdk.example') as staged:
        dockerfile = (staged.path / 'Dockerfile').read_text()
        assert 'pip --isolated install' not in dockerfile
        assert 'ENV KUMA_DISABLE_UPDATE_CHECK=1' in dockerfile
        assert 'COPY requirement.md /opt/agent/requirement.md' in dockerfile
        assert calls[0][0].name == 'whitelist.json'
        assert calls[0][1][1]['url'] == 'https://sdk.example/sdk/*'

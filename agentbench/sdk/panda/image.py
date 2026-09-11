"""Stage only Panda source into an isolated copy of the selected Agent."""
import re
import shutil
import tempfile
from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path
from agentbench.runtime.docker.worker_build import _ignore


@contextmanager
def evaluation_agent(agent, sdk):
    sdk = sdk.resolve(strict=True)
    if not (sdk / 'src/panda_sdk/__init__.py').is_file():
        raise ValueError('Panda SDK source unavailable')
    with tempfile.TemporaryDirectory(prefix='abb-panda-') as temporary:
        root = Path(temporary) / 'agent-unit'
        shutil.copytree(agent.path, root, ignore=_ignore, symlinks=True)
        staged = root / '.abb-sdk'
        staged.mkdir()
        for name in ('pyproject.toml', 'README.md'):
            shutil.copy2(sdk / name, staged / name, follow_symlinks=False)
        shutil.copytree(sdk / 'src', staged / 'src', ignore=_ignore, symlinks=True)
        if any(path.is_symlink() for path in root.rglob('*')):
            raise ValueError('Panda build may not contain symlinks')
        source = (root / 'agent.toml').read_text()
        source, count = re.subn(r'(?m)^argv = .*$',
            'argv = ["python", "-m", "agentbench.sdk.panda.worker"]', source)
        if count != 1:
            raise ValueError('Expected one launch.argv')
        # Separate evaluation credentials from target model routing.
        if re.search(r'(?m)^env_keys\s*=', source):
            source = re.sub(r'(?m)^(env_keys\s*=\s*\[)',
                r'\1"PANDA_API_KEY", "PANDA_MODEL", ', source)
        else:
            source = source.replace('[runtime]\n',
                '[runtime]\nenv_keys = ["PANDA_API_KEY", "PANDA_MODEL"]\n', 1)
        source += '\n[[llm_interception.tool_routes]]\npurpose = "evaluation"\nhost_patterns = ["openrouter.ai"]\nports = [443]\nmethods = ["POST"]\npath_patterns = ["/api/v1/chat/completions"]\n'
        (root / 'agent.toml').write_text(source)
        dockerfile = root / 'Dockerfile'
        original = dockerfile.read_text()
        users = re.findall(r'(?im)^USER\s+(.+)$', original)
        if not users or users[-1].strip() in ('root', '0'):
            raise ValueError('Panda requires a non-root Agent image')
        dockerfile.write_text(original + '\nUSER root\nCOPY .abb-sdk/ /opt/panda-sdk/\n'
            'RUN python -m pip install --no-cache-dir /opt/panda-sdk\n'
            'COPY evaluation/ /opt/agent/evaluation/\nUSER ' + users[-1] + '\n')
        yield SimpleNamespace(path=root, agent_id=agent.agent_id, framework=agent.framework)

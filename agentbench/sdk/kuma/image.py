"""Isolated evaluation build overlay; original Agent/network files stay untouched."""
from contextlib import contextmanager
from pathlib import Path
import re
import shutil
import tempfile
from types import SimpleNamespace
from agentbench.runtime.docker.worker_build import _ignore


@contextmanager
def evaluation_agent(agent, sdk):
    sdk = sdk.resolve(strict=True)
    if (sdk / 'src').is_symlink():
        raise ValueError('SDK src cannot be a symlink')
    for name in ('pyproject.toml', 'README.md', 'src/kuma/__init__.py'):
        if not (sdk / name).is_file() or (sdk / name).is_symlink():
            raise ValueError('Invalid local KUMA SDK source')
    with tempfile.TemporaryDirectory(prefix='abb-evaluation-') as temporary:
        root = Path(temporary) / 'agent-unit'
        shutil.copytree(agent.path, root, ignore=_ignore, symlinks=True)
        if any(p.is_symlink() for p in root.rglob('*')):
            raise ValueError('Agent source must not contain symlinks')
        # SDK atomically updates .gitignore unless this rule already exists.
        # Prepare it in the build copy so the runtime source remains read-only.
        ignore_file = root / 'agent/.gitignore'
        if ignore_file.is_symlink():
            raise ValueError('Agent ignore file cannot be a symlink')
        existing = ignore_file.read_text() if ignore_file.exists() else ''
        if not {'.kuma/', '/.kuma/'}.intersection(line.strip() for line in existing.splitlines()):
            ignore_file.write_text(existing + '\n/.kuma/\n')
        staged_sdk = root / '.abb-sdk'
        staged_sdk.mkdir()
        for name in ('pyproject.toml', 'README.md'):
            shutil.copy2(sdk / name, staged_sdk / name)
        shutil.copytree(sdk / 'src', staged_sdk / 'src', ignore=_ignore, symlinks=True)
        if any(p.is_symlink() for p in root.rglob('*')):
            raise ValueError('Evaluation build must not contain symlinks')
        source = (root / 'agent.toml').read_text()
        source, count = re.subn(r'(?m)^argv = .*$',
                               'argv = ["python", "-m", "agentbench.sdk.kuma.worker"]', source)
        if count != 1:
            raise ValueError('Expected one explicit launch.argv')
        source = source.replace('[runtime]\n', '[runtime]\nenv_keys = ["KUMA_API_KEY", "DEFUZEX_API_KEY"]\n', 1)
        # User-authorized SDK-only egress, scoped to this evaluation overlay.
        # No model routes/protocols are changed and no unrestricted network is used.
        source += '\n[[llm_interception.tool_routes]]\npurpose = "evaluation"\nhost_patterns = ["defuzex.ai"]\nports = [443]\nmethods = ["GET", "POST"]\npath_patterns = ["/api/agentdefuze", "/api/agentdefuze/*"]\n'
        (root / 'agent.toml').write_text(source)
        dockerfile = root / 'Dockerfile'
        original = dockerfile.read_text()
        users = re.findall(r'(?im)^USER\s+(.+)$', original)
        if not users or users[-1].strip() in ('root', '0'):
            raise ValueError('Evaluation requires an explicit non-root image USER')
        dockerfile.write_text(original + '\nUSER root\nCOPY .abb-sdk/ /opt/abb-sdk/\n'
                             'RUN python -m pip install --no-cache-dir "/opt/abb-sdk[otel]"\n'
                             'COPY evaluation/ /opt/agent/evaluation/\nUSER ' + users[-1] + '\n')
        yield SimpleNamespace(path=root, agent_id=agent.agent_id, framework=agent.framework)

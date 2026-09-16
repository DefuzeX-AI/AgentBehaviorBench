"""Isolated evaluation build overlay; original Agent/network files stay untouched."""
from contextlib import contextmanager
from pathlib import Path
import re
import shutil
import tempfile
from types import SimpleNamespace
from agentbench.runtime.docker.worker_build import _ignore
from agentbench.sdk.common.whitelist import whitelist_toml
from .configuration import DEFAULT_BASE_URL
from .manifest import extend_runtime_environment

# The SDK has to land in the interpreter the worker runs: whatever `python` the Agent
# image's PATH resolves to. That interpreter need not have pip -- a uv-created venv
# first on PATH has none. ensurepip installs pip from the standard library's bundled
# wheel, so bootstrapping needs no network. If neither exists, name the interpreter.
SDK_INSTALL = (
    'RUN interpreter="$(command -v python)" '
    '|| { echo "ABB evaluation overlay: no python on the image PATH" >&2; exit 1; }; '
    'python -m pip --version >/dev/null 2>&1 '
    '|| python -m ensurepip --default-pip >/dev/null '
    '|| { echo "ABB evaluation overlay: $interpreter has no pip module and no ensurepip;'
    ' install pip into that interpreter in the Agent Dockerfile" >&2; exit 1; }; '
    'python -m pip --isolated install --no-cache-dir '
    '--index-url https://pypi.org/simple '
    '-r /opt/abb-sdk/requirements.txt\n'
)


@contextmanager
def evaluation_agent(agent, *, control=None, deadline=None, backend=DEFAULT_BASE_URL):
    """Stage an Agent and install the adapter's pinned PyPI SDK in its image.

    The host does not need an SDK checkout or installation. Dependencies belong
    to this adapter and are installed only while building the evaluation image.
    The Agent source and its original Dockerfile remain unchanged. ``backend`` is
    the normalized KUMA Backend URL; the container receives KUMA_BASE_URL and its
    egress admits exactly that Backend.
    """
    requirements = Path(__file__).with_name('requirements.txt')
    def check():
        if control is not None:
            control.check()
        if deadline is not None:
            deadline.check()
    def checked_copy(source, target):
        check()
        with open(source, 'rb') as incoming, open(target, 'wb') as outgoing:
            while chunk := incoming.read(1024 * 1024):
                check()
                outgoing.write(chunk)
        shutil.copystat(source, target)
        return target
    check()
    if not requirements.is_file() or requirements.is_symlink():
        raise ValueError('KUMA adapter requirements.txt is missing or linked')
    with tempfile.TemporaryDirectory(prefix='abb-evaluation-') as temporary:
        root = Path(temporary) / 'agent-unit'
        shutil.copytree(agent.path, root, ignore=_ignore, symlinks=True,
                        copy_function=checked_copy)
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
        shutil.copy2(requirements, staged_sdk / 'requirements.txt')
        if any(p.is_symlink() for p in root.rglob('*')):
            raise ValueError('Evaluation build must not contain symlinks')
        source = (root / 'agent.toml').read_text()
        source, count = re.subn(r'(?m)^argv = .*$',
                               f'argv = ["python", "-m", "{__package__}.worker"]', source)
        if count != 1:
            raise ValueError('Expected one explicit launch.argv')
        source = extend_runtime_environment(source, ('KUMA_API_KEY', 'DEFUZEX_API_KEY', 'KUMA_BASE_URL'))
        source += whitelist_toml(Path(__file__).with_name('whitelist.json'), (
            {'url': backend, 'methods': ['GET', 'POST']},
            {'url': backend + '/*', 'methods': ['GET', 'POST']}))
        (root / 'agent.toml').write_text(source)
        dockerfile = root / 'Dockerfile'
        original = dockerfile.read_text()
        users = re.findall(r'(?im)^USER\s+(.+)$', original)
        if not users or users[-1].strip() in ('root', '0'):
            raise ValueError('Evaluation requires an explicit non-root image USER')
        # Optional profile schemas or fixtures may live here; text-input Agents
        # do not need to create an otherwise empty directory for Docker COPY.
        evaluation_copy = ('COPY evaluation/ /opt/agent/evaluation/\n'
                           if (root / 'evaluation').is_dir() else '')
        dockerfile.write_text(original + '\nUSER root\nCOPY .abb-sdk/ /opt/abb-sdk/\n'
                             + SDK_INSTALL +
                             'COPY requirement.md /opt/agent/requirement.md\n'
                             + evaluation_copy + 'USER ' + users[-1] + '\n')
        check()
        yield SimpleNamespace(path=root, agent_id=agent.agent_id, framework=agent.framework)

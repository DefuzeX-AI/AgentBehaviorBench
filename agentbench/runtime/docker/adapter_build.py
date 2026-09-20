"""Stage optional registered framework dependencies in the actual worker interpreter."""
import re
from pathlib import Path
from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY
from agentbench.runtime.agentcontainer.config import tomllib


def stage_adapter_dependencies(config, context, dockerfile):
    manifest = tomllib.loads((config.agent_root / 'agent.toml').read_text())
    requirements = DEFAULT_ADAPTER_FACTORY.build_requirements(manifest.get('framework', 'langgraph'))
    if requirements is None:
        return
    requirements = Path(requirements)
    if requirements.is_symlink() or not requirements.is_file():
        raise ValueError('Registered adapter requirements must be a regular file')
    destination = context / '.abb-adapter'
    destination.mkdir(exist_ok=True)
    (destination / 'requirements.txt').write_bytes(requirements.read_bytes())
    source = dockerfile.read_text()
    users = re.findall(r'(?im)^USER\s+(.+)$', source)
    if not users or users[-1].strip() in ('root', '0', '0:0'):
        raise ValueError('Adapter overlay requires an explicit non-root image USER')
    dockerfile.write_text(source + '\nUSER root\n'
        'COPY .abb-adapter/requirements.txt /opt/abb-adapter/requirements.txt\n'
        'RUN python -m pip --version >/dev/null 2>&1 || python -m ensurepip --default-pip\n'
        'RUN python -m pip --isolated install --no-cache-dir --index-url https://pypi.org/simple '
        '-r /opt/abb-adapter/requirements.txt\nUSER ' + users[-1] + '\n')

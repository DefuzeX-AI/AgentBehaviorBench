"""Build Company + local KUMA SDK and verify both imports offline.

Run from the ABB repository: python -m tests.acceptance.company_sdk.run
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.docker.image_builder import DockerImageBuilder
from agentbench.runtime.docker.worker_build import worker_build_context, _ignore
from agentbench.runtime.docker.policy import DockerPolicy


def main():
    acceptance = Path(__file__).resolve().parent
    repo = acceptance.parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-source', type=Path, default=repo.parent / 'Defuze-SDK')
    args = parser.parse_args()
    sdk = args.sdk_source.resolve(strict=True)
    for name in ('pyproject.toml', 'README.md', 'src/kuma/__init__.py'):
        if not (sdk / name).is_file():
            raise ValueError(f'Not a local KUMA SDK source: missing {name}')
    config = AgentContainerConfig.from_agent_dir(
        repo / 'resources/agents/01-company-research-agent',
        secret_resolver=EnvironmentSecretResolver({'TAVILY_API_KEY': 'offline-import-only'}))
    with worker_build_context(config) as (context, dockerfile):
        base = DockerImageBuilder().build(context=context, dockerfile=dockerfile,
                                          repository='company-research-agent')
    print(f'Company base: {base}', flush=True)
    with tempfile.TemporaryDirectory(prefix='abb-company-sdk-') as temporary:
        context = Path(temporary)
        source = context / 'sdk'
        source.mkdir()
        # Only packaging inputs, never the workspace, credentials or run artifacts.
        for name in ('pyproject.toml', 'README.md'):
            if (sdk / name).is_symlink():
                raise ValueError(f'SDK packaging file cannot be a symlink: {name}')
            shutil.copy2(sdk / name, source / name)
        if (sdk / 'src').is_symlink():
            raise ValueError('SDK src cannot be a symlink')
        shutil.copytree(sdk / 'src', source / 'src', ignore=_ignore, symlinks=True)
        if any(p.is_symlink() for p in source.rglob('*')):
            raise ValueError('SDK source must not contain symlinks')
        shutil.copy2(acceptance / 'Dockerfile', context / 'Dockerfile')
        shutil.copy2(acceptance / 'verify_imports.py', context / 'verify_imports.py')
        iid = context / 'image-id'
        subprocess.run(['docker', 'build', '--build-arg', f'COMPANY_IMAGE={base}',
                        '--iidfile', str(iid), str(context)], check=True)
        image = iid.read_text().strip()
    print(f'Company + SDK image: {image}', flush=True)
    subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                    *DockerPolicy().run_arguments(), image,
                    'python', '/opt/abb-checks/verify_imports.py'], check=True)


if __name__ == '__main__':
    main()

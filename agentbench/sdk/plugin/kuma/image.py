"""KUMA configuration for the shared evaluation image overlay."""

from contextlib import contextmanager
from pathlib import Path

from agentbench.runtime.docker.evaluation_image import SDK_INSTALL, evaluation_image
from agentbench.sdk.common.whitelist import append_whitelist
from .configuration import DEFAULT_BASE_URL


SDK_ENVIRONMENT = ('KUMA_API_KEY', 'DEFUZEX_API_KEY', 'KUMA_BASE_URL')


@contextmanager
def evaluation_agent(agent, *, control=None, deadline=None, backend=DEFAULT_BASE_URL,
                     worker_package=__package__, sdk_environment=SDK_ENVIRONMENT,
                     require_profile=True):
    """Install KUMA and declare its controller, credentials, routes and Profile.

    Local providers reuse the same SDK with ``backend=None`` and their own worker
    package. ``require_profile=False`` copies requirement.md only when supplied.
    """
    backend_routes = () if backend is None else (
        {'url': backend, 'methods': ['GET', 'POST']},
        {'url': backend + '/sdk/*', 'methods': ['GET', 'POST']})

    def configure_manifest(source):
        return append_whitelist(source, Path(__file__).with_name('whitelist.json'), backend_routes)

    optional_files = tuple(name for name, present in (
        ('requirement.md', (agent.path / 'requirement.md').is_file()),
        ('evaluation', (agent.path / 'evaluation').is_dir()),
    ) if present)
    with evaluation_image(
        agent, requirements=Path(__file__).with_name('requirements.txt'),
        worker_module=worker_package + '.worker', control=control, deadline=deadline,
        worker_environment=sdk_environment, manifest_transform=configure_manifest,
        image_environment=('KUMA_DISABLE_UPDATE_CHECK=1',),
        required_files=('requirement.md',) if require_profile else (),
        optional_files=optional_files, install_command=SDK_INSTALL,
    ) as staged:
        yield staged

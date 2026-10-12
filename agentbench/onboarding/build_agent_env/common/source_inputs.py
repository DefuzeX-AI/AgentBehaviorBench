"""Check durable installation inputs before onboarding consumes local source."""
from agentbench.runtime.source.config import source_spec, InstallSource
from agentbench.runtime.source.preparation import prepare_installation_inputs
from .errors import BuildError
from ..openrouter_provider.context import safe_file
from agentbench.runtime.agentcontainer.config import tomllib


def prepare_inputs(root, manifest=None):
    try:
        path = safe_file(root, "agent.toml")
        if manifest is None and path is not None:
            try:
                manifest = tomllib.loads(path.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError:
                # The per-file stage owns unfinished manual configuration and
                # records a resumable conflict without replacing that file.
                manifest = None
        spec = source_spec(manifest) if manifest is not None else None
        prepare_installation_inputs(root, required=isinstance(spec, InstallSource))
    except (OSError, ValueError) as exc:
        raise BuildError(str(exc)) from exc

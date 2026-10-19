"""Declarative implementation of EvaluationSDKPlugin for ordinary SDKRun factories."""
from functools import partial
from pathlib import Path
from agentbench.sdk.contracts import RunnerConcurrencyCapabilities


class ContainerSDKPlugin:
    """Export an instance as plugin; its directory still supplies its name.

    The factory reference is imported only by the isolated worker. A plugin
    declaration has no dependency on the vendor package or a running service.
    """
    execution = 'container'
    implicit_selection = False
    concurrency_capabilities = RunnerConcurrencyCapabilities(isolated_cases=True, cooperative_cancel=True)

    def __init__(self, *, create_run, requirements, documents=(), worker_environment=(),
                 whitelist=None):
        module, separator, name = create_run.partition(':')
        if not separator or not name.isidentifier() or not all(part.isidentifier() for part in module.split('.')):
            raise ValueError('SDK factory must be a module:function reference')
        self.create_run = create_run
        self.requirements = Path(requirements)
        self.documents = tuple(documents)
        self.worker_environment = tuple(worker_environment)
        self.whitelist = Path(whitelist) if whitelist is not None else None

    def stage_agent(self, agent, **kwargs):
        from agentbench.runtime.docker.evaluation_image import evaluation_image
        from agentbench.sdk.common.whitelist import append_whitelist
        transform = partial(append_whitelist, path=self.whitelist) if self.whitelist else None
        return evaluation_image(agent, requirements=self.requirements,
            worker_module='agentbench.sdk.integration.worker', required_files=self.documents,
            optional_files=('evaluation',), worker_environment=self.worker_environment,
            manifest_transform=transform, **kwargs)

    def create_benchmark_runner(self, *, context, options):
        from .runner import ContainerSDKRunner
        return ContainerSDKRunner(self, context=context, options=options)

"""Explicit native execution plugin. Judge runs on the host after cleanup."""
from pathlib import Path
from agentbench.sdk.integration.plugin import ContainerSDKPlugin


class NativePlugin(ContainerSDKPlugin):
    execution_only = True

    def create_benchmark_runner(self, *, context, options):
        from .runner import NativeRunner
        return NativeRunner(self, context=context, options=options)


plugin = NativePlugin(create_run='agentbench.sdk.plugin.native.backend:create_run',
                      requirements=Path(__file__).with_name('requirements.txt'))

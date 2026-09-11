"""Select Panda's independent evaluation runner."""
from ..contracts import SDKRunnerContext
from ..plugins import SDK_PLUGIN_API_VERSION


class PandaEvaluationSDK:
    name = "panda"
    api_version = SDK_PLUGIN_API_VERSION
    execution = "container"

    def create_benchmark_runner(self, *, context: SDKRunnerContext, options):
        from .benchmark import PandaContainerRunner
        return PandaContainerRunner(context=context, options=options)


plugin = PandaEvaluationSDK()

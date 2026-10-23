"""Independent local testing method using ABB execution and a host model Judge."""
from pathlib import Path
from agentbench.sdk.plugin.native.plugin import NativePlugin


class LocalEvaluationSDK(NativePlugin):
    def execution_configuration(self, *, environ, model, options):
        from .relay import judge_model
        environment = dict(environ)
        if model is not None:
            environment['ABB_MODEL'] = model
        selected = judge_model(environment)
        return {'judge': {'base_url': selected.base_url, 'model': selected.model},
                'implementation': 'abb-local-v2'}

    def create_benchmark_runner(self, *, context, options):
        from .native_runner import LocalRunner
        return LocalRunner(self, context=context, options=options)


plugin = LocalEvaluationSDK(create_run='agentbench.sdk.plugin.native.backend:create_run',
                           requirements=Path(__file__).with_name('requirements.txt'))

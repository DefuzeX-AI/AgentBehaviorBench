"""Local fixed-case generation and optional imported cases over native execution."""
from dataclasses import replace
from agentbench.sdk.plugin.native.runner import NativeRunner
from .cases import DEFAULT_MAX_STEPS
from .generation import generate_cases, agent_context
from agentbench.sdk.integration.runner import accepted, read
from .relay import judge_model


class LocalRunner(NativeRunner):
    def __init__(self, plugin, *, context, options):
        if context.model is not None:
            context = replace(context, environ={**context.environ, 'ABB_MODEL': context.model})
        options = dict(options)
        options.setdefault('judge', 'local')
        super().__init__(plugin, context=context, options=options)

    def validate_sdk(self, registration):
        judge_model(self.context.environ)
        return super().validate_sdk(registration)

    def prepare_cases(self, registration, **kwargs):
        if 'cases' not in self.sdk_options:
            limit = self.sdk_options.get('max_steps') or getattr(registration, 'max_steps', None) or DEFAULT_MAX_STEPS
            self.validate_sdk(registration)
            directory = self._run(registration, context=self.context, on_progress=kwargs.get('on_progress'),
                settings=self._settings(registration, mode='context', agent_context=agent_context(registration)),
                execute_agent=False)
            accepted(directory, execution=False)
            public_context = read(directory / 'agent-context.json')
            self.sdk_options['cases'] = generate_cases(registration, limit=limit,
                environ=self.context.environ, output=self.output, context=public_context)
        return super().prepare_cases(registration, **kwargs)

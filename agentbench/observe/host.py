"""Host framework evidence; never manufactures interceptor or SDK wire data."""
import asyncio
from pathlib import Path
from uuid import uuid4
from .invocation import InvocationObservation
from .store import atomic_json, json_value, redact


class HostObservation:
    def __init__(self, root, registration, sdk_run):
        self.directory = Path(root).resolve() / uuid4().hex
        self.directory.mkdir(parents=True, mode=0o700)
        self.agent, self.run = registration, sdk_run
        self.step = 0
        self.metadata = {'schema': 'abb.evaluate.run.v1', 'run_id': self.directory.name,
                         'agent_id': registration.agent_id, 'sdk_run_id': sdk_run.run_id, 'status': 'running',
                         'evidence_availability': {
                             'framework': {'status': 'pending'}, 'otel': {'status': 'pending'},
                             'network': {'status': 'unavailable', 'reason': 'Host execution has no interceptor capture'},
                             'sdk_wire': {'status': 'unavailable', 'reason': 'SDK did not provide private wire evidence'}}}
        self._save()

    def _save(self):
        import os
        secrets = tuple(v for k, v in os.environ.items() if any(x in k.upper() for x in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')))
        atomic_json(self.directory / 'run.json', redact(json_value(self.metadata), secrets))

    async def invoke(self, running, test_input, config):
        self.step += 1
        folder = self.directory / 'evaluation' / 'inputs' / f'{self.step:04d}'
        invocation_id = uuid4().hex
        context = {'agent_id': self.agent.agent_id, 'input_id': test_input.input_id,
                   'invocation_id': invocation_id, 'sdk_run_id': self.run.run_id}
        observed = InvocationObservation(folder, invocation_id, self.run.run_id, self.agent.framework, context=context)
        store = observed.store
        secrets = getattr(getattr(store, 'store', store), '_secrets', ())
        atomic_json(folder / 'input.json', redact(json_value({'input_id': test_input.input_id, 'payload': test_input.payload}), secrets))
        result = {'schema': 'abb.result.v1', 'run_id': invocation_id, **context}
        try:
            store.record('execution_start', input=test_input.payload)
            invocation = await running.ainvoke(test_input.payload, run_config=observed.config(config))
            result.update(status='succeeded', output=invocation.output, raw_output=invocation.raw_output)
            store.record('execution_end', output=invocation.output)
            return invocation
        except BaseException as exc:
            result.update(status='cancelled' if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)) else 'failed', error_type=type(exc).__name__, error=str(exc))
            store.record('execution_error', error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            atomic_json(folder / 'result.json', redact(json_value(result), secrets))
            observed.close()
            import json
            otel = json.loads((folder / 'otel-status.json').read_text())
            self.metadata['evidence_availability']['framework'] = {'status': 'available'}
            self.metadata['evidence_availability']['otel'] = {
                'status': 'available' if otel['status'] == 'complete' else otel['status'],
                'reason': otel.get('reason') or otel.get('error')}
            self._save()

    def finish(self, result=None, error=None):
        self.metadata['status'] = ('cancelled' if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)) else 'failed') if error else 'succeeded'
        if error:
            self.metadata['error_type'] = type(error).__name__
        if result is not None:
            # Public SDK contract only; no provider-specific file discovery.
            self.metadata['evaluation_result'] = {'run_id': result.run_id, 'history_count': result.history_count,
                'report': {key: json_value(getattr(result.report, key, None))
                           for key in ('status', 'confidence', 'issues', 'evidence_gaps')} if result.report else None}
        self._save()


def host_observation_factory(root):
    """Observe the Agent from the host only when it runs in this process.

    A containerised Agent already records framework and OTel evidence from its
    own worker, and its run_config crosses a JSON process boundary that cannot
    carry LangChain callbacks, so attaching a host observer to one makes the
    invocation envelope unserialisable.
    """
    from agentbench.runtime.agentcontainer.config import runtime_type

    def observe(registration, sdk_run):
        if runtime_type(registration.path) != "in_process":
            return None
        return HostObservation(root, registration, sdk_run)

    return observe

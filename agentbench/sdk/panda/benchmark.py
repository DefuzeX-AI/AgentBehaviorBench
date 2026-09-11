"""Host orchestration and acceptance of Panda container artifacts."""
import json
import math
from pathlib import Path
from dataclasses import dataclass
from uuid import uuid4
from dotenv import dotenv_values
from agentbench.adapter import AdapterInvocation
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult
from agentbench.harness.progress import emit_progress
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.interception import OpenRouterProvider
from agentbench.sdk.common.artifacts import Artifacts
from .image import evaluation_agent


@dataclass(frozen=True)
class PandaReport:
    status: str
    confidence: float
    issues: tuple
    evidence_gaps: tuple
    run_id: str
    case_id: str
    extensions: dict


class PandaContainerRunner:
    def __init__(self, *, context, options):
        self.context = context
        self.options = dict(options)
        unknown = set(options) - {'sdk_source', 'output', 'timeout', 'provider', 'env_file',
            'model', 'steps', 'max_steps', 'case_prompt', 'payload', 'expected_output'}
        if unknown:
            raise ValueError(f'Unknown Panda options: {sorted(unknown)}')
        self.sdk = Path(self.options.pop('sdk_source', Path(__file__).resolve().parents[4] / 'panda-sdk'))
        self.output = Path(self.options.pop('output', 'results/observe'))
        self.timeout = self.options.pop('timeout', 600)
        if type(self.timeout) not in (int, float) or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError('timeout must be positive and finite')
        values = dotenv_values(self.options.pop('env_file')) if 'env_file' in self.options else {}
        self.environ = dict(context.environ)
        self.environ['PANDA_API_KEY'] = values.get('OPENROUTER_API_KEY') or self.environ.get('OPENROUTER_API_KEY', '')
        self.environ['PANDA_MODEL'] = self.options.pop('model', None) or values.get('OPENROUTER_MODEL') or self.environ.get('OPENROUTER_MODEL', '')
        if 'max_steps' in self.options:
            self.options['steps'] = self.options.pop('max_steps')

    def validate_sdk(self, registration):
        if not (self.sdk / 'src/panda_sdk/__init__.py').is_file():
            raise ValueError('Panda SDK source unavailable')
        if not (registration.path / 'evaluation/input-contract.json').is_file():
            raise ValueError('Agent needs evaluation/input-contract.json')
        if self.options.get('provider') == 'openrouter' and not all(self.environ.get(k) for k in ('PANDA_API_KEY', 'PANDA_MODEL')):
            raise ValueError('Panda OpenRouter key and model are required')
        return 'panda-container'

    def run(self, registration, *, on_progress=None, on_step_start=None,
            on_step_complete=None, on_step_failure=None):
        self.validate_sdk(registration)
        directory = self.output.resolve() / uuid4().hex
        files = Artifacts(directory)
        files.save('request/evaluation.json', self.options)
        destination = directory / 'evaluation'
        destination.mkdir(mode=0o777)
        destination.chmod(0o777)
        status = {'schema': 'abb.evaluate.run.v1', 'run_id': directory.name,
                  'agent_id': registration.agent_id, 'status': 'running', 'sdk': 'panda'}
        files.save('run.json', status)
        emit_progress(on_progress, stage='benchmark_execution', status='started',
            agent_id=registration.agent_id, artifact_directory=str(directory))
        runtime = DockerRuntime(environ=self.environ,
            model_provider=OpenRouterProvider(model=self.context.model),
            trace_sink=self.context.trace_sink, trace_max_bytes=self.context.trace_max_bytes)
        session = None
        try:
            with evaluation_agent(registration, self.sdk) as descriptor:
                session = runtime.start(descriptor, invocation=(directory / 'request', destination))
                code = session.wait(timeout=self.timeout)
                if code != 0:
                    raise RuntimeError(f'Panda worker failed; artifacts: {directory}')
                session.validate_trace(0)
            result = read_result(directory, registration.agent_id)
            for step in result.steps:
                if on_step_start:
                    on_step_start(registration.agent_id, step.input_id, step.payload)
                if on_step_complete:
                    on_step_complete(registration.agent_id, step)
            status['status'] = 'succeeded'
            return result
        except Exception:
            status['status'] = 'failed'
            raise
        finally:
            if session is not None:
                session.close()
                files.save('diagnostics.json', {'stdout': session.stdout, 'stderr': session.stderr})
            files.save('run.json', status)


def read_result(directory, agent_id):
    def read(relative):
        path = directory / 'evaluation' / relative
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Artifact outside result directory')
        return json.loads(path.read_text())
    summary, case, report = read('manifest.json'), read('case.json'), read('judge/report.json')
    if (summary.get('phase') != 'finished' or summary.get('execution') != 'succeeded'
        or summary.get('judge') != 'received' or summary.get('agent_id') != agent_id
        or report.get('run_id') != summary.get('run_id')
        or report.get('case_id') != case.get('case_id') or case.get('case_id') != summary.get('case_id')
        or report.get('status') not in ('pass', 'issue')):
        raise ValueError('Incomplete Panda evaluation or identity mismatch')
    ids = [item['input_id'] for item in case['inputs']]
    if not ids or len(set(ids)) != len(ids) or ids != [step['input_id'] for step in summary['steps']]:
        raise ValueError('Incomplete Panda input history')
    steps = []
    for index, step in enumerate(summary['steps'], 1):
        folder = f'inputs/{index:04d}'
        request, result, submission, item = (read(f'{folder}/{name}.json') for name in ('request', 'result', 'submission', 'input'))
        if (result.get('status') != 'succeeded' or result.get('agent_id') != agent_id
            or request.get('agent_id') != agent_id or result.get('run_id') != request.get('run_id')
            or request.get('session_id') != summary['run_id'] or submission.get('status') != 'completed'
            or submission.get('input_id') != step['input_id'] or item != case['inputs'][index - 1]
            or submission.get('output') != result.get('output')):
            raise ValueError('Panda submission identity mismatch')
        steps.append(BenchmarkStepResult(item['input_id'], item['payload'],
            AdapterInvocation(result['output'], result.get('raw_output'))))
    normalized = PandaReport(report['status'], report['confidence'], tuple(report.get('issues', [])),
        tuple(report.get('evidence_gaps', [])), report['run_id'], report['case_id'],
        {'abb_artifact_directory': str(directory)})
    return BenchmarkResult(agent_id, 'ContainerAgentAdapter', summary['run_id'], 'report_ready',
                           normalized, tuple(steps), len(steps), 'panda-container')

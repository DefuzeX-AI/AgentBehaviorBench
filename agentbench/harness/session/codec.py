"""Version-neutral JSON shapes shared by Suite recovery and result exports."""

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from types import MappingProxyType

from agentbench.adapter import AdapterInvocation
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult, CaseResult
from agentbench.sdk.contracts import PreparedCase


def json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [json_value(item) for item in value]
    if is_dataclass(value):
        return {field.name: json_value(getattr(value, field.name)) for field in fields(value)}
    for method in ('model_dump', 'dict'):
        converter = getattr(value, method, None)
        if callable(converter):
            return json_value(converter())
    if hasattr(value, '__dict__'):
        return json_value(vars(value))
    return repr(value)


@dataclass(frozen=True)
class RecoveredReport:
    """Keep the entire SDK report without importing its provider-specific model."""

    payload: Mapping

    def __getattr__(self, name):
        payload = object.__getattribute__(self, 'payload')
        if name in payload:
            return payload[name]
        if name in {'issues', 'evidence_gaps'}:
            return ()
        if name == 'confidence':
            return None
        raise AttributeError(name)


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def report_to_json(report):
    if report is None:
        return None
    if isinstance(report, RecoveredReport):
        return json_value(report.payload)
    value = json_value(report)
    value = value if isinstance(value, dict) else {}
    for field in ('status', 'confidence', 'issues', 'evidence_gaps'):
        if hasattr(report, field):
            value[field] = json_value(getattr(report, field))
    return value


def benchmark_to_json(benchmark):
    return {'agent_id': benchmark.agent_id, 'adapter_name': benchmark.adapter_name,
            'run_id': benchmark.run_id, 'run_state': benchmark.run_state,
            'provider_mode': benchmark.provider_mode, 'passed': benchmark.passed,
            'history_count': benchmark.history_count, 'report': report_to_json(benchmark.report),
            'steps': [{'input_id': step.input_id, 'payload': json_value(step.payload),
                       'output': json_value(step.invocation.output),
                       'raw_output': json_value(step.invocation.raw_output)} for step in benchmark.steps]}


def case_to_json(case):
    value = {'agent_id': case.agent_id, 'case_index': case.case_index,
             'job_id': case.job_id, 'case_id': case.case_id, 'status': case.status,
             'artifacts': json_value(case.artifacts),
             'benchmark': None if case.benchmark is None else benchmark_to_json(case.benchmark),
             'error': None if case.error_type is None else
                 {'type': case.error_type, 'message': case.error_message}}
    for name in ('attempt_id', 'attempt_number', 'execution_status', 'judge_status'):
        if hasattr(case, name):
            value[name] = json_value(getattr(case, name))
    return value


def benchmark_from_json(value):
    report = value.get('report')
    if report is not None:
        if not isinstance(report, dict) or not isinstance(report.get('status'), str):
            raise ValueError('Stored benchmark report requires a status')
        report = RecoveredReport(_freeze(report))
    steps = tuple(BenchmarkStepResult(step['input_id'], step.get('payload'),
                                     AdapterInvocation(step.get('output'), step.get('raw_output')))
                  for step in value.get('steps', ()))
    return BenchmarkResult(value['agent_id'], value['adapter_name'], value['run_id'],
                           value['run_state'], report, steps, value['history_count'],
                           value.get('provider_mode'))


def case_from_json(value):
    """Restore public DTOs, including a non-passing but completed Judge report."""
    benchmark = value.get('benchmark')
    error = value.get('error') or {}
    extra = {name: value[name] for name in ('attempt_id', 'attempt_number')
             if name in value and name in {field.name for field in fields(CaseResult)}}
    return CaseResult(value['agent_id'], value['case_index'], value['job_id'], value['status'],
                      value.get('case_id'), None if benchmark is None else benchmark_from_json(benchmark),
                      error.get('type'), error.get('message'), value.get('artifacts'), **extra)


def prepared_from_json(value):
    path = value.get('artifact_path')
    return PreparedCase(value['case_index'], value.get('case_id'),
                        None if path is None else Path(path), value.get('content_sha256'),
                        value.get('artifact_sha256'), value.get('environment_sha256'))


def event_to_json(event):
    value = dict(event)
    if isinstance(value.get('case_result'), CaseResult):
        value['case_result'] = case_to_json(value['case_result'])
    item = value.get('item')
    if item is not None and hasattr(item, 'case_results'):
        value['item'] = {**json_value(item), 'status': item.status,
                         'case_results': [case_to_json(case) for case in item.case_results]}
    return json_value(value)

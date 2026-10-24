"""Offline SDK controller using only ABB's shared execution facilities."""
import asyncio
import importlib.abc
import json
from pathlib import Path
import sys


class NoVendorImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'kuma' or fullname.startswith(('kuma.', 'agentbench.sdk.plugin.kuma')):
            raise AssertionError('Independent SDK imported a vendor: ' + fullname)


sys.meta_path.insert(0, NoVendorImports())

from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.common.output_permissions import share_output
from agentbench.sdk.integration.agent import ManagedAgentSession


class Evidence:
    def __init__(self):
        self.spans = []

    def accept_span(self, span):
        self.spans.append({'trace_id': format(span.context.trace_id, '032x'),
                           'span_id': format(span.context.span_id, '016x'),
                           'name': span.name})


async def execute():
    output = Path('/run/abb-output')
    settings = json.loads(Path('/run/abb-input/evaluation.json').read_text())
    files = Artifacts(output, environ={})
    case = json.loads((Path(settings['private_storage']) / settings['case_file']).read_text())
    files.save('case.json', case)
    evidence, results = Evidence(), []
    async with ManagedAgentSession(output=output, settings=settings) as agent:
        for index, value in enumerate(case['inputs'], 1):
            envelope = {'schema': 'abb.invocation.v1', 'run_id': f'invocation-{index}',
                        'session_id': case['case_id'], 'agent_id': settings['agent_id'],
                        'framework': 'langgraph', 'input': value,
                        'observation_context': {'case_id': case['case_id'], 'input_id': str(index)}}
            result = await agent.invoke(envelope, output / 'steps' / f'{index:04d}', evidence)
            results.append(result['output'])
    assert evidence.spans, 'Original Agent spans must reach the independent SDK'
    files.save('evidence.json', evidence.spans)
    files.save('judge/report.json', {'status': 'pass' if results == case['expected'] else 'issue',
                                   'confidence': 1.0, 'issues': [], 'evidence_gaps': [],
                                   'case_id': case['case_id'], 'outputs': results})
    files.save('manifest.json', {'run_id': case['case_id'], 'case_id': case['case_id'],
                                 'execution': 'succeeded', 'judge': 'received'})
    files.save('verification.json', {'vendor_imported': any(
        name == 'kuma' or name.startswith(('kuma.', 'agentbench.sdk.plugin.kuma'))
        for name in sys.modules), 'span_count': len(evidence.spans)})


if __name__ == '__main__':
    output = Path('/run/abb-output')
    try:
        asyncio.run(execute())
    except BaseException as error:
        Artifacts(output).save('error.json', {'error_type': type(error).__name__, 'error': str(error)})
        raise
    finally:
        share_output(output)

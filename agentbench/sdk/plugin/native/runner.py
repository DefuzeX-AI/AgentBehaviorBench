"""Import user cases and reuse ABB's isolated runtime and evidence validation."""
from dataclasses import replace
import json
from pathlib import Path

from agentbench.sdk.integration.runner import ContainerSDKRunner, read
from agentbench.sdk.judgment import DeferredJudgment
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.judges import build_request, execute_judge, resolve_judge
from .backend import validate_case


class NativeRunner(ContainerSDKRunner):
    def __init__(self, plugin, *, context, options):
        options = dict(options)
        self.judge_reference = options.pop('judge', None)
        self.judge = resolve_judge(self.judge_reference) if self.judge_reference else None
        self.supports_deferred_judgment = self.judge is not None
        source = options.pop('case_file', None)
        self.source = source
        if source is not None and Path(source).is_file():
            if 'cases' in options:
                raise ValueError('Use case_file or cases, not both')
            document = json.loads(Path(source).read_text(encoding='utf-8-sig'))
            if not isinstance(document, dict) or document.get('schema') != 'abb.cases.v1':
                raise ValueError('Expected abb.cases.v1 collection')
            options['cases'] = document.get('cases')
        if 'cases' in options:
            if not isinstance(options['cases'], list) or not options['cases']:
                raise ValueError('Case collection must be a non-empty list')
            options['cases'] = [validate_case(case) for case in options['cases']]
            ids = [case['case_id'] for case in options['cases']]
            if len(ids) != len(set(ids)):
                raise ValueError('Case IDs must be unique')
        super().__init__(plugin, context=context, options=options)

    def prepare_cases(self, registration, **kwargs):
        cases = self.sdk_options.get('cases', [])
        if len(cases) != registration.case_count:
            raise ValueError('Imported case count must match --cases or the registry count')
        limit = self.sdk_options.get('max_steps', getattr(registration, 'max_steps', None))
        if limit is not None and any(len(case['inputs']) > limit for case in cases):
            raise ValueError('Imported Case exceeds step budget; raise --max-steps explicitly')
        return super().prepare_cases(registration, **kwargs)

    def _read_result(self, directory, registration, case, document):
        result = super()._read_result(directory, registration, case, document)
        manifest = read(Path(directory) / 'manifest.json')
        expected = document['case']['inputs']
        if len(manifest['steps']) > len(expected):
            raise ValueError('Execution exceeds the imported Case')
        for index, step in enumerate(manifest['steps']):
            actual = read(Path(directory) / step['directory'] / 'input.json')
            if actual != {key: expected[index][key] for key in ('input_id', 'payload')}:
                raise ValueError('Executed input differs from the imported Case')
        if len(manifest['steps']) != len(expected) and not result.failures:
            raise ValueError('Imported Case stopped without an execution failure')
        return result

    def run_case(self, registration, case, **kwargs):
        result = super().run_case(registration, case, **kwargs)
        return self._assess(self.directory, registration, case, result)

    def execute_case(self, registration, case, **kwargs):
        super().run_case(registration, case, **kwargs)
        self._request(self.directory, registration, json.loads(case.artifact_path.read_bytes()))
        return DeferredJudgment(self.directory)

    def judge_case(self, registration, case, ticket, **kwargs):
        document = json.loads(case.artifact_path.read_bytes())
        result = self._read_result(ticket.directory, registration, case, document)
        return self._assess(ticket.directory, registration, case, result)

    def _request(self, directory, registration, document):
        request = build_request(directory, registration, document)
        from agentbench.sdk.integration.cases import case_bytes, digest
        request['judge'] = self.judge_reference
        request['request_id'] = digest(case_bytes({k: v for k, v in request.items() if k != 'request_id'}))
        files = Artifacts(directory, environ=self.context.environ)
        saved = Path(directory) / 'judge/request.json'
        if saved.exists() and json.loads(saved.read_bytes()) != request:
            raise ValueError('Saved Judge request differs; keep each assessment separate')
        files.save('judge/request.json', request)
        return request

    def _assess(self, directory, registration, case, result):
        request = self._request(directory, registration, json.loads(case.artifact_path.read_bytes()))
        if self.judge is None:
            return replace(result, judge_delivery_status='not_requested')
        report = execute_judge(self.judge, request, directory=directory,
                               environ=self.context.environ)
        return replace(result, report=report, judge_delivery_status='received')

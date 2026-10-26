"""Optional KUMA Judge adapter for already-executed ABB evidence.

No Agent invocation or case generation occurs here. KUMA imports are lazy and
only this adapter owns the translation to its public contracts.
"""
import json


def context_from_request(request, directory):
    from kuma import Case, KumaInput, Submission, HistoryItem, CaptureStatus
    from kuma.providers import JudgeContext
    from kuma.otel import configure_trace_evidence
    from opentelemetry.sdk.trace import TracerProvider
    from agentbench.sdk.integration.telemetry import decode_span
    from kuma.evidence.runtime import build_runtime_evidence, runtime_submission_id

    run_id, case_id = request['run_id'], request['case']['case_id']
    kinds = {'text' if isinstance(item['payload'], str) else 'structured' for item in request['case']['inputs']}
    if len(kinds) != 1:
        raise ValueError('KUMA requires a homogeneous text or structured Case; ABB execution supports mixed inputs')
    kind = next(iter(kinds))
    inputs = tuple(KumaInput(run_id, case_id, item['input_id'], index,
                            kind, item['payload'])
                   for index, item in enumerate(request['case']['inputs']))
    case = Case(inputs, case_id=case_id, input_type=kind)
    provider = TracerProvider()
    capture = configure_trace_evidence(provider)
    history = []
    try:
        for item, step in zip(inputs, request['steps']):
            if item.input_id != step['input']['input_id']:
                raise ValueError('ABB evidence does not match its Case')
            capture.begin_step(run_id, case_id, item.input_id)
            with (directory / step['evidence_prefix'] / 'spans.jsonl').open(encoding='utf-8') as stream:
                for line in stream:
                    capture.export_span(decode_span(json.loads(line)))
            prepared = capture.prepare_step(run_id, case_id, item.input_id)
            result = step['result']
            status = {'succeeded': 'completed', 'cancelled': 'aborted'}.get(result['status'], result['status'])
            runtime = build_runtime_evidence(
                run_id=run_id, input_id=item.input_id, step_id=item.input_id,
                submission_id=runtime_submission_id(run_id, item.input_id), root=directory,
                status=status, output=result.get('output'), error=result.get('error'),
                file_evidence=None, logs=(), trace_evidence=prepared.evidence)
            submission = Submission(run_id, case_id, item.input_id, status,
                output=result.get('output'), error=result.get('error'),
                capture_status=CaptureStatus(traces=prepared.component),
                missing=prepared.missing + runtime.missing,
                dropped_count=prepared.dropped_count + runtime.dropped_count,
                extensions={'trace_evidence': prepared.evidence,
                            'runtime_evidence': runtime.evidence,
                            'runtime_file_sources': runtime.file_sources,
                            'file_observation_summary': runtime.file_summary})
            history.append(HistoryItem(item, submission))
            prepared.commit()
        return JudgeContext(case, tuple(history), 'completed',
                            {'abb_request_id': request['request_id'], 'file_capture': 'not_provided'})
    finally:
        provider.shutdown()


class KumaJudge:
    def judge(self, request, *, directory, environ):
        from kuma.providers import OfficialJudgeProvider, normalize_report
        from kuma.transport.backend import BackendClient
        from kuma import to_json
        from .configuration import api_key, backend_url
        credential, _ = api_key(environ)
        context = context_from_request(request, directory)
        client = BackendClient(api_key=credential, base_url=backend_url(environ))
        provider = OfficialJudgeProvider(client, state_root=directory / 'judge-state')
        report = to_json(normalize_report(provider.judge(context), run_id=request['run_id']))
        return {'schema': 'abb.judge.result.v1', 'request_id': request['request_id'],
                'status': report['status'], 'confidence': report.get('confidence'),
                'issues': report.get('issues', []), 'evidence_gaps': report.get('evidence_gaps', [])}


judge = KumaJudge()

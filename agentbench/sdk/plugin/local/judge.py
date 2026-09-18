"""Local Judge: Run facts decided in the container, coherence by the host's model.

The Judge is an SDK Judge provider, so it runs inside the Agent container. There
the model interceptor rejects any model call lacking the run's own credential and
records an accepted one as Agent evidence, and the upstream key must never enter
the container. The container therefore calls no model: it writes one bounded
request beside its artifacts and waits for the host, which holds the key, to
answer it (see ``relay.py``).
"""
import json
import time
from pathlib import Path

from agentbench.observe.store import atomic_json
from agentbench.sdk.common.artifacts import plain

REQUEST = 'local-judge-request.json'
RESPONSE = 'local-judge-response.json'
REQUEST_SCHEMA = 'abb.local_judge.request.v1'
RESPONSE_SCHEMA = 'abb.local_judge.response.v1'
JUDGE = 'abb-local-judge-v1'
TEXT_LIMIT = 4000
CONFIDENCE = ('low', 'medium', 'high')


def bounded(value, limit=TEXT_LIMIT):
    """Return model-facing text: strings unchanged, other values as JSON, truncated."""
    if not isinstance(value, str):
        value = json.dumps(plain(value), ensure_ascii=False, sort_keys=True, default=str)
    return value if len(value) <= limit else value[:limit] + '…'


def write_shared(path, value):
    """Write atomically and readable across the bind mount."""
    atomic_json(path, value)
    # Host and container may run as different users; the reader needs no write access.
    path.chmod(0o644)


def verdict_fields(value, input_ids):
    """Normalize a model verdict; ValueError unless it decides pass or issue."""
    if not isinstance(value, dict) or value.get('status') not in ('pass', 'issue'):
        raise ValueError('The Judge verdict needs status "pass" or "issue"')
    confidence = value.get('confidence')
    reason = bounded(str(value.get('reason') or '').strip(), 500)
    issues = []
    if value['status'] == 'issue':
        for issue in value.get('issues') or ():
            message = str(issue.get('message') or '').strip() if isinstance(issue, dict) else ''
            if message:
                item = {'severity': 'medium', 'message': bounded(message, 500)}
                if issue.get('input_id') in input_ids:
                    item['input_id'] = issue['input_id']
                issues.append(item)
        issues = issues[:20] or [{'severity': 'medium', 'message': reason or 'The Judge reported an issue.'}]
    return {'status': value['status'], 'confidence': confidence if confidence in CONFIDENCE else 'medium',
            'reason': reason, 'issues': issues}


def step_facts(item):
    """Project one committed history item onto what the Judge decides from."""
    submission = plain(item.submission)
    evidence = (submission.get('extensions') or {}).get('trace_evidence')
    spans = evidence.get('spans') if isinstance(evidence, dict) else None
    traces = ((submission.get('capture_status') or {}).get('traces') or {}).get('status', 'missing')
    count = len(spans) if isinstance(spans, list) else 0
    return {'input_id': submission['input_id'], 'status': submission['status'],
            'trace_status': traces, 'trace_spans': count,
            'traced': traces in ('complete', 'partial') and count > 0,
            'input': bounded(plain(item.test_input).get('payload')),
            'output': bounded(submission.get('output'))}


def report(status, confidence, extensions, *, issues=(), gaps=()):
    # ABB accepts a report only when its extensions name the executed Case.
    return {'status': status, 'confidence': confidence, 'stop_reason': 'case_completed',
            'issues': list(issues), 'evidence_gaps': list(gaps), 'extensions': extensions}


class LocalJudge:
    """SDK Judge provider: failures and missing traces decide first, then the host's model."""

    def __init__(self, directory, *, timeout=300.0, interval=0.25):
        self.directory = Path(directory)
        self.timeout = timeout
        self.interval = interval

    def judge(self, context):
        steps = [step_facts(item) for item in context.history]
        facts = {'case_id': context.case.case_id, 'judge': JUDGE,
                 'steps': [{key: step[key] for key in ('input_id', 'status', 'trace_status', 'trace_spans')}
                           for step in steps]}
        failed = [step for step in steps if step['status'] != 'completed']
        if failed:
            return report('issue', 'high', {**facts, 'decided_by': 'run_status'}, issues=[
                {'severity': 'high', 'input_id': step['input_id'],
                 'message': f"The Agent step ended as {step['status']}."} for step in failed])
        untraced = [step for step in steps if not step['traced']]
        if untraced or not steps:
            return report('insufficient_evidence', 'high', {**facts, 'decided_by': 'trace_capture'}, gaps=[
                {'input_id': step['input_id'],
                 'message': f"No SDK trace evidence ({step['trace_status']}, {step['trace_spans']} spans)."}
                for step in untraced] or [{'message': 'The Run submitted no steps.'}])
        verdict = self.ask_host({'schema': REQUEST_SCHEMA, 'case_id': context.case.case_id,
                                 'steps': [{key: step[key] for key in ('input_id', 'input', 'output')}
                                           for step in steps]}, {step['input_id'] for step in steps})
        return report(verdict['status'], verdict['confidence'],
                      {**facts, 'decided_by': 'model', 'model': verdict['model'], 'reason': verdict['reason']},
                      issues=verdict['issues'])

    def ask_host(self, request, input_ids):
        """Publish one request and wait for the host's verdict."""
        from kuma.errors import ProviderError
        response = self.directory / RESPONSE
        write_shared(self.directory / REQUEST, request)
        deadline = time.monotonic() + self.timeout
        while not response.is_file():
            if time.monotonic() >= deadline:
                raise ProviderError(f'The host answered no local Judge request within {self.timeout:g}s')
            time.sleep(self.interval)
        try:
            answer = json.loads(response.read_text(encoding='utf-8'))
            if not isinstance(answer, dict) or answer.get('schema') != RESPONSE_SCHEMA:
                raise ValueError('unexpected answer schema')
        except (OSError, ValueError) as exc:
            raise ProviderError(f'The host returned an unreadable local Judge answer: {exc}') from None
        if answer.get('error'):
            raise ProviderError(f"The local Judge model call failed: {bounded(str(answer['error']), 500)}")
        try:
            return {**verdict_fields(answer, input_ids), 'model': str(answer.get('model') or '')}
        except ValueError as exc:
            raise ProviderError(str(exc)) from None

"""Read bounded, identity-checked Kuma diagnostics without replacing failures."""
import json
import os
from pathlib import Path
import unicodedata

from agentbench.sdk.common.artifacts import Artifacts
from agentbench.observe.store import redact


def artifact_path(directory, relative):
    """Resolve an existing file inside the trusted run; reject symlink components."""
    root = Path(directory).resolve()
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Diagnostic path must be relative to the run')
    candidate = root / relative
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not candidate.is_file():
        raise ValueError('Diagnostic path outside run')
    current = candidate
    while current != root:
        if current.is_symlink():
            raise ValueError('Linked diagnostic file')
        current = current.parent
    return resolved


def read_diagnostic(directory, relative):
    """Return a diagnostic object, or an empty object if absent/unsafe/malformed.

    An empty object does not mean the artifact is absent; use unreadable_reason()
    where a required artifact must not be mistaken for one that was never written.
    """
    try:
        path = artifact_path(directory, relative)
        with path.open('rb') as stream:
            payload = stream.read(8 * 1024 * 1024 + 1)
        if len(payload) > 8 * 1024 * 1024:
            return {}
        value = json.loads(payload)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, RuntimeError):
        return {}


# Artifacts whose absence changes what a failure means. An unreadable one is
# reported as such instead of being folded into "no diagnostics".
REQUIRED_ARTIFACTS = ('evaluation/manifest.json', 'evaluation/error.json',
                      'evaluation/case-collection.json', 'evaluation/case.json',
                      'evaluation/judge/report.json')


def unreadable_reason(directory, relative):
    """Explain why an existing artifact cannot be read; None if readable or absent."""
    candidate = Path(directory) / relative
    try:
        if not candidate.exists() and not candidate.is_symlink():
            return None
    except OSError as exc:
        return f'{relative}: {exc.strerror or type(exc).__name__}'
    try:
        path = artifact_path(directory, relative)
        with path.open('rb'):
            return None
    except FileNotFoundError:
        return None
    except OSError as exc:
        detail = exc.strerror or type(exc).__name__
        try:
            info = candidate.stat()
        except OSError:
            return f'{relative}: {detail}'
        getuid = getattr(os, 'getuid', None)
        host = f'; host uid {getuid()}' if getuid is not None else ''
        return (f'{relative}: {detail} (owner uid {info.st_uid}, '
                f'mode {info.st_mode & 0o777:04o}{host})')
    except (ValueError, RuntimeError) as exc:
        return f'{relative}: {exc}'


def _text(value, limit=500):
    if not isinstance(value, (str, int, float, bool)):
        return None
    return ''.join(c if unicodedata.category(c) != 'Cc' else ' ' for c in str(value))[:limit]


def collect_artifacts(directory, host, *, environ=None):
    """Collect safe SDK errors and a received report independently of acceptance.

    Args:
        directory: Trusted host directory containing this invocation's artifacts.
        host: Host-owned identity/status, including the selected Case when known.
        environ: Frozen environment used solely to redact configured secrets.
    Returns:
        JSON-safe diagnostics and an optional identity-checked report reference.
        A report reference does not turn host rejection into benchmark success.
    I/O:
        Reads local files only. Missing or malformed diagnostics are tolerated.
    """
    files = Artifacts(Path(directory), environ=environ)
    summary = read_diagnostic(directory, 'evaluation/manifest.json')
    early = read_diagnostic(directory, 'evaluation/error.json')
    error = summary.get('error')
    if not isinstance(error, dict):
        error = early
    result = {'directory': str(Path(directory).resolve()), 'phase': _text(summary.get('phase') or early.get('phase')),
              'cleanup_status': host.get('cleanup_status'),
              'host_trace_validation': host.get('host_trace_validation'),
              'safe_case_replay': host.get('safe_case_replay') is True,
              'host_phase': host.get('phase'), 'host_error_type': host.get('error_type'),
              'completion': {key: summary.get(key) for key in ('execution', 'otel', 'submission', 'evidence')}}
    unreadable = [reason for relative in REQUIRED_ARTIFACTS
                  if (reason := unreadable_reason(directory, relative)) is not None]
    if unreadable:
        result['unreadable_artifacts'] = [_text(reason) for reason in unreadable]
    if error:
        result['sdk_error'] = {key: (value if isinstance(value, bool) else _text(value))
                               for key in ('type', 'message', 'code', 'retryable', 'request_id', 'client_request_id')
                               if (value := error.get(key)) is not None}
    steps = summary.get('steps')
    for step in steps if isinstance(steps, list) else ():
        if not isinstance(step, dict) or not isinstance(step.get('directory'), str):
            continue
        native = read_diagnostic(directory, f"evaluation/{step['directory']}/result.json")
        if native.get('status') in ('failed', 'timeout'):
            result['native_failure'] = {key: _text(native.get(key)) for key in ('status', 'error_type', 'error')}
            break
    report = read_diagnostic(directory, 'evaluation/judge/report.json')
    case = read_diagnostic(directory, 'evaluation/case.json')
    case_id, run_id = summary.get('case_id'), summary.get('run_id')
    request = summary.get('request')
    if (isinstance(request, dict) and request.get('request_type') == 'judgment'
            and isinstance(case_id, str) and case_id and isinstance(run_id, str) and run_id
            and request.get('run_id') == run_id and request.get('case_id') == case_id
            and case.get('case_id') == case_id and host.get('case_id') in (None, case_id)):
        result['sdk_request'] = {key: request.get(key) for key in (
            'client_request_id', 'request_type', 'status', 'operation_id', 'run_id', 'case_id')}
    extensions = report.get('extensions')
    if (summary.get('judge') == 'received' and isinstance(case_id, str) and case_id
            and isinstance(run_id, str) and run_id and case.get('case_id') == case_id
            and report.get('run_id') == run_id and isinstance(extensions, dict)
            and extensions.get('case_id') == case_id and host.get('case_id') in (None, case_id)
            and report.get('status') in ('pass', 'issue', 'insufficient_evidence')
            and isinstance(report.get('report_id'), str) and report['report_id']):
        result['received_report'] = {
            'status': report['status'], 'report_id': _text(report['report_id']),
            'run_id': _text(run_id), 'case_id': _text(case_id),
            'path': 'evaluation/judge/report.json', 'host_accepted': host.get('status') == 'succeeded',
        }
    related = []
    try:
        path = artifact_path(directory, 'network.jsonl')
        with path.open('rb') as stream:
            size = stream.seek(0, 2)
            stream.seek(max(0, size - 2 * 1024 * 1024))
            tail = stream.read(2 * 1024 * 1024)
            rows = tail.splitlines()
            if size > 2 * 1024 * 1024:
                rows = rows[1:]  # Drop a possibly incomplete leading event.
        for row in rows:
            try:
                event = json.loads(row)
            except ValueError:
                continue
            if not isinstance(event, dict) or event.get('event') not in ('llm_error', 'tool_error'):
                continue
            data = event.get('data')
            if not isinstance(data, dict):
                continue
            if any(host.get(k) is not None and data.get(k) not in (None, host[k]) for k in ('job_id', 'case_id')):
                continue
            # These are related observations, not a claim that the last error
            # caused the SDK exception. The two channels keep their own codes.
            detail = {key: _text(data.get(key)) for key in (
                'error_code', 'error_stage', 'call_id', 'request_id', 'method', 'error') if data.get(key) is not None}
            detail['host'] = _text(data.get('source_host') or data.get('host'))
            raw_path = data.get('source_path') or data.get('path')
            detail['path'] = _text(raw_path.split('?', 1)[0].split('#', 1)[0]) if isinstance(raw_path, str) else None
            related.append(detail)
        if related:
            result['related_network_errors'] = related[-3:]
    except (OSError, ValueError, RuntimeError):
        pass
    from .recovery import classify_failure
    result['recovery'] = classify_failure(result)
    return redact(result, files.secrets)


def failure_message(artifacts):
    """Describe SDK classification first, then label related network evidence."""
    error = artifacts.get('sdk_error', {})
    parts = [f'unreadable artifact {reason}' for reason in artifacts.get('unreadable_artifacts', ())]
    if error:
        parts.append(f"{error.get('type', 'SDK error')} [{error.get('code', 'unknown')}]: {error.get('message', '')}")
    for item in artifacts.get('related_network_errors', ()):
        parts.append(f"related network: {item.get('error_code') or 'unclassified'} "
                     f"{item.get('method') or ''} {item.get('host') or ''}{item.get('path') or ''}: {item.get('error') or ''}")
    if report := artifacts.get('received_report'):
        parts.append(f"Judge already received: {report['status']} ({report['path']}); host accepted={report['host_accepted']}")
    return '; '.join(parts)


def evaluation_failure(directory, message, *, environ=None):
    """Build a runtime error carrying artifacts for the generic Case exporter."""
    host = read_diagnostic(directory, 'run.json')
    artifacts = collect_artifacts(directory, host, environ=environ)
    detail = failure_message(artifacts)
    error = RuntimeError(f'{message}: {directory}' + (f' — {detail}' if detail else ''))
    error.artifacts = artifacts
    return error

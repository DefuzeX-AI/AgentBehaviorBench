"""Public SDK request recovery; never recreate a paid Run or replay the Agent."""
from .configuration import api_key, request_options
from .diagnostics import read_diagnostic


def inspect_requests(repo_path, client_request_id=None):
    """Read non-secret SDK request records from the original repository ledger."""
    from kuma import list_requests, show_request
    if client_request_id is not None:
        return show_request(client_request_id, repo_path=repo_path).to_dict()
    return [record.to_dict() for record in list_requests(repo_path)]


def recover_request(repo_path, client_request_id, *, environ, base_url,
                    expected_run_id=None, expected_case_id=None, options=None):
    """Resume the original operation using the official public recovery API.

    Args:
        repo_path: Original repository retaining its .kuma/requests ledger.
        client_request_id: Exact kreq_ recovery ID, not the HTTP request ID.
        environ: Original credential mapping; only its selected key is forwarded.
        base_url: Original Backend URL. SDK validates Backend/key binding.
        expected_run_id: Optional original Run ID to verify before and after I/O.
        expected_case_id: Optional original Case ID, checked before and after I/O.
        options: Explicit public HTTP/retry/wait settings.
    Returns:
        A public request record and an optional recovered Judge report. Host
        acceptance is always False here; the original evidence still needs it.
        CaseGen recovery does not promise a reusable Case artifact.
    Raises:
        ValueError: On identity mismatch or an unsafe/mismatched report.
        KumaError: SDK lookup/poll/authentication failures, including
            request_not_started; none trigger a new create_run or Agent call.
    """
    from kuma import show_request, resume_request

    def check(record):
        for key, expected in (('run_id', expected_run_id), ('case_id', expected_case_id)):
            if expected is not None and getattr(record, key) != expected:
                raise ValueError(f'Recovery {key} does not match the original request')

    check(show_request(client_request_id, repo_path=repo_path))
    credential, _ = api_key(environ)
    record = resume_request(client_request_id, repo_path=repo_path, api_key=credential,
                            base_url=base_url, **request_options(options))
    check(record)
    report = None
    if record.status == 'succeeded' and record.request_type == 'judgment':
        if not record.result_locator:
            raise ValueError('Recovered Judge request has no public report locator')
        report = read_diagnostic(repo_path, record.result_locator)
        extensions = report.get('extensions')
        if (report.get('run_id') != record.run_id or not isinstance(extensions, dict) or extensions.get('case_id') != record.case_id
                or report.get('status') not in ('pass', 'issue', 'insufficient_evidence')):
            raise ValueError('Recovered Judge report does not match the original request')
    return {'request': record.to_dict(), 'report': report, 'host_accepted': False}

"""Public SDK request recovery; never recreate a paid Run or replay the Agent."""
import errno
import os
import stat
from pathlib import Path

from .configuration import api_key, request_options
from .diagnostics import read_diagnostic


def ledger_access_error(repo_path, client_request_id=None):
    """Return a PermissionError naming an unreadable ledger path, owner and mode.

    The SDK stores request records owner-only and reports any read failure as an
    unreadable record, which is also what corruption looks like. A record written
    by a different uid is a permission problem with a known remedy, so name it
    before the SDK is asked to read it. Absent ledgers stay the SDK's to report.
    """
    directory = Path(repo_path) / '.kuma' / 'requests'
    try:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            return None
        names = os.listdir(directory)
        if client_request_id is not None:
            candidates = [directory / f'{client_request_id}.json']
        else:
            candidates = [directory / name for name in sorted(names)
                          if name.startswith('kreq_') and name.endswith('.json')]
    except FileNotFoundError:
        return None
    except PermissionError:
        return _ledger_permission_error(directory)
    for path in candidates:
        try:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                continue
            if stat.S_ISDIR(mode):
                os.listdir(path)
            else:
                path.open('rb').close()
        except FileNotFoundError:
            continue
        except PermissionError:
            return _ledger_permission_error(path)
    return None


def _ledger_permission_error(path):
    getuid = getattr(os, 'getuid', None)
    reader = f'host uid {getuid()}' if getuid is not None else 'this host user'
    try:
        info = path.stat()
        owner = f'owned by uid {info.st_uid} with mode {info.st_mode & 0o777:04o}'
    except OSError:
        owner = 'owner unknown'
    return PermissionError(
        errno.EACCES, f'SDK request ledger is not readable by {reader} ({owner}); '
        'the original records must be readable by the host user before recovery', str(path))


def inspect_requests(repo_path, client_request_id=None):
    """Read non-secret SDK request records from the original repository ledger."""
    from kuma import list_requests, show_request
    if (error := ledger_access_error(repo_path, client_request_id)) is not None:
        raise error
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

    if (error := ledger_access_error(repo_path, client_request_id)) is not None:
        raise error
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

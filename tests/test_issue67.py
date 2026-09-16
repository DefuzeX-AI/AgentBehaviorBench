"""Issue #67: an unreadable SDK request ledger is reported as a permission problem."""
import json
import pathlib

import pytest

from agentbench.sdk.plugin.kuma.request_recovery import (
    inspect_requests, ledger_access_error, recover_request,
)

REQUEST_ID = 'kreq_' + 'b' * 32


def _ledger(tmp_path):
    directory = tmp_path / '.kuma' / 'requests'
    directory.mkdir(parents=True)
    record = directory / f'{REQUEST_ID}.json'
    record.write_text(json.dumps({'client_request_id': REQUEST_ID}))
    record.chmod(0o600)  # The SDK stores records owner-only by design.
    return record


def _deny(monkeypatch, target):
    original = pathlib.Path.open

    def open_(self, *args, **kwargs):
        if self == target:
            raise PermissionError(13, 'Permission denied', str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, 'open', open_)


def test_recovery_names_owner_and_mode_before_the_sdk_reads_the_record(tmp_path, monkeypatch):
    import kuma
    record = _ledger(tmp_path)
    _deny(monkeypatch, record)
    monkeypatch.setattr(kuma, 'show_request', lambda *a, **kw: pytest.fail('SDK would hide the cause'))
    monkeypatch.setattr(kuma, 'resume_request', lambda *a, **kw: pytest.fail('must not contact service'))
    with pytest.raises(PermissionError) as raised:
        recover_request(tmp_path, REQUEST_ID, environ={'KUMA_API_KEY': 'offline'},
                        base_url='https://sdk.example')
    assert raised.value.filename == str(record)
    assert 'mode 0600' in str(raised.value) and 'owned by uid' in str(raised.value)
    assert 'host user' in str(raised.value)


def test_inspection_reports_the_same_permission_problem(tmp_path, monkeypatch):
    import kuma
    record = _ledger(tmp_path)
    _deny(monkeypatch, record)
    monkeypatch.setattr(kuma, 'list_requests', lambda *a, **kw: pytest.fail('SDK would hide the cause'))
    with pytest.raises(PermissionError, match='not readable'):
        inspect_requests(tmp_path)


def test_readable_or_absent_ledgers_are_left_to_the_sdk(tmp_path):
    assert ledger_access_error(tmp_path, REQUEST_ID) is None
    _ledger(tmp_path)
    assert ledger_access_error(tmp_path, REQUEST_ID) is None
    assert ledger_access_error(tmp_path) is None
    assert ledger_access_error(tmp_path, 'kreq_' + 'c' * 32) is None

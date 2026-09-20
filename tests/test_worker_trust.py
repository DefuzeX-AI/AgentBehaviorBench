"""Native Node agents must not depend on a transitive Python HTTP CA package."""
import sys
import ssl
from pathlib import Path
from types import SimpleNamespace
from agentbench.runtime.agentcontainer import worker


def test_trust_uses_system_roots_when_certifi_is_absent(tmp_path, monkeypatch):
    system = tmp_path / 'system.pem'; system.write_bytes(b'public-roots')
    intercept = tmp_path / 'interceptor.pem'; intercept.write_bytes(b'local-interceptor')
    monkeypatch.setitem(sys.modules, 'certifi', None)
    monkeypatch.setattr(ssl, 'get_default_verify_paths', lambda: SimpleNamespace(openssl_cafile=str(system)))
    monkeypatch.setenv('SSL_CERT_FILE', str(intercept))
    real_path = Path
    monkeypatch.setattr(worker, 'Path', lambda value: tmp_path / 'bundle.pem' if value == '/tmp/abb-ca-bundle.pem' else real_path(value))
    worker.configure_trust()
    assert (tmp_path / 'bundle.pem').read_bytes() == b'public-roots\nlocal-interceptor'

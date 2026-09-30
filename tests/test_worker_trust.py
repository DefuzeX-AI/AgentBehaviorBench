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


def test_git_and_curl_trust_the_same_bundle(tmp_path, monkeypatch):
    """git (libcurl-gnutls) and the curl CLI ignore SSL_CERT_FILE; they need their own variables."""
    from agentbench.runtime.interception.plugins import PemEnvironmentTrust
    env = PemEnvironmentTrust().agent_environment('/run/defuzex-ca/ca.pem')
    assert env['GIT_SSL_CAINFO'] == env['CURL_CA_BUNDLE'] == '/run/defuzex-ca/ca.pem'
    system = tmp_path / 'system.pem'; system.write_bytes(b'public-roots')
    intercept = tmp_path / 'interceptor.pem'; intercept.write_bytes(b'local-interceptor')
    monkeypatch.setitem(sys.modules, 'certifi', None)
    monkeypatch.setattr(ssl, 'get_default_verify_paths', lambda: SimpleNamespace(openssl_cafile=str(system)))
    for key in env:
        monkeypatch.setenv(key, str(intercept))
    real_path = Path
    bundle = tmp_path / 'bundle.pem'
    monkeypatch.setattr(worker, 'Path', lambda value: bundle if value == '/tmp/abb-ca-bundle.pem' else real_path(value))
    worker.configure_trust()
    import os
    assert os.environ['GIT_SSL_CAINFO'] == os.environ['CURL_CA_BUNDLE'] == str(bundle)
    assert os.environ['NODE_EXTRA_CA_CERTS'] == str(intercept)  # Node appends extra CAs to its own roots


def test_acp_children_receive_git_and_curl_trust(monkeypatch):
    from agentbench.adapter.acp.process import TRUST_KEYS
    assert {'GIT_SSL_CAINFO', 'CURL_CA_BUNDLE'} <= set(TRUST_KEYS)

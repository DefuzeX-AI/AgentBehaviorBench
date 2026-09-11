"""Production interceptor startup/export/cleanup, with no external API calls."""
import os
import ssl
from uuid import uuid4
import pytest

@pytest.mark.skipif(os.getenv('ABB_DOCKER_TEST') != '1', reason='Opt-in real Docker lifecycle')
@pytest.mark.parametrize('export_fails', [False, True])
def test_private_ca_stays_in_container(repo_root, monkeypatch, export_fails):
    from agentbench.runtime.docker.runtime import DockerRuntime
    from agentbench.runtime.interception import InterceptionConfig, InterceptionTraceState
    runtime = DockerRuntime(environ={'OPENROUTER_API_KEY': 'offline-placeholder', 'OPENROUTER_MODEL': 'fixture/model'})
    config = InterceptionConfig.from_agent_dir(repo_root / 'resources/agents/01-company-research-agent')
    suffix = 'ca-test-' + uuid4().hex[:10]
    network = 'abb-' + suffix
    runtime._run('network', 'create', network)
    interceptor = None
    try:
        if export_fails:
            def fail_export(*args):
                raise RuntimeError('fixture export failed')
            monkeypatch.setattr(runtime, '_export_ca', fail_export)
            with pytest.raises(RuntimeError, match='fixture export failed'):
                runtime._start_interceptor(agent_id='fixture', interception=config, suffix=suffix,
                    network_name=network, trace_state=InterceptionTraceState())
            assert runtime._run_quiet('inspect', 'defuzex-' + suffix + '-interceptor', capture=True).returncode != 0
            return
        interceptor, tokens = runtime._start_interceptor(agent_id='fixture', interception=config,
            suffix=suffix, network_name=network, trace_state=InterceptionTraceState())
        certificate = interceptor.ca_certificate
        ssl.create_default_context(cafile=str(certificate))
        assert certificate.stat().st_uid == os.getuid()
        assert [p.name for p in certificate.parent.iterdir()] == ['mitmproxy-ca-cert.pem']
        assert 'PRIVATE KEY' not in certificate.read_text()
        details = runtime._run('inspect', '--format', '{{json .HostConfig}}', interceptor.container_name).stdout
        assert 'DAC_OVERRIDE' not in details and 'CHOWN' not in details
        assert str(certificate.parent) not in details
        assert tokens
    finally:
        if interceptor:
            interceptor.close()
            assert not certificate.parent.exists()
        runtime._run('network', 'rm', network)

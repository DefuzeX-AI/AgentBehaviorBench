"""The first native failure, including abort, is primary diagnostic evidence."""
import json
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.plugin.kuma.diagnostics import collect_artifacts, failure_message


def test_cancelled_step_is_named_and_update_check_is_not_related(tmp_path):
    files = Artifacts(tmp_path, environ={})
    files.save('evaluation/manifest.json', {'execution': 'failed', 'steps': [
        {'input_id': 'step-5', 'directory': 'inputs/0005'}, {'input_id': 'step-6', 'directory': 'inputs/0006'}]})
    files.save('evaluation/inputs/0005/result.json', {'status': 'cancelled', 'error_type': 'CancelledError', 'error': ''})
    files.save('evaluation/inputs/0006/result.json', {'status': 'failed', 'error_type': 'RuntimeError', 'error': 'ACP adapter is closed'})
    (tmp_path / 'network.jsonl').write_text(json.dumps({'event': 'tool_error', 'data': {
        'method': 'GET', 'host': 'api.github.com', 'path': '/repos/DefuzeX-AI/KUMA-DefuzeX/releases/latest',
        'error_code': 'transport_error', 'error': 'Client disconnected.'}})+'\n')
    artifacts = collect_artifacts(tmp_path, {}, environ={})
    assert artifacts['native_failure']['status'] == 'cancelled'
    assert artifacts['native_failure']['input_id'] == 'step-5'
    assert failure_message(artifacts).startswith('Agent step-5 CancelledError')
    assert 'related network' not in failure_message(artifacts)

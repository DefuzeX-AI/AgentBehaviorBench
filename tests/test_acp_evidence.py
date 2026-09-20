"""Wire callbacks and actual OTel exports, including honest missing content."""
import asyncio
import json
from dataclasses import replace
from pathlib import Path
import sys
import pytest
pytest.importorskip('acp')
pytest.importorskip('opentelemetry.sdk')
from agentbench.adapter.acp import ACPAdapter
from agentbench.adapter.acp.config import ACPConfig
from agentbench.adapter.acp.filesystem import read_file, write_file
from agentbench.adapter.acp.terminal import Terminals
from agentbench.observe.invocation import InvocationObservation

SERVER = Path(__file__).parent / 'acp_fixtures/server.py'

@pytest.mark.parametrize('policy', ['deny', 'allow_once'])
def test_callbacks_produce_actual_tool_spans_and_file_evidence(tmp_path, policy):
    config = ACPConfig(tmp_path, (sys.executable, str(SERVER)), str(tmp_path),
                       permission_policy=policy, timeout=5, cleanup_timeout=.2)
    observer = InvocationObservation(tmp_path / 'trace', 'inv', 'case', 'acp')
    observer.store.record('execution_start', input='callbacks')
    adapter = ACPAdapter(config)
    try:
        result = adapter.invoke('callbacks', run_config=observer.config())
        observer.store.record('execution_end', output=result.output)
    finally:
        adapter.close()
        observer.close()
    spans = [json.loads(line)['data'] for line in (tmp_path / 'trace/otel.jsonl').read_text().splitlines()]
    tool = next(s for s in spans if s['attributes'].get('abb.kind') == 'tool')
    attrs = tool['attributes']
    assert tool['parent_span_id'] is not None
    assert attrs['gen_ai.tool.call.id'] == 't1'
    assert not any(s['attributes'].get('gen_ai.operation.name') == 'chat' for s in spans)
    if policy == 'allow_once':
        assert result.output == 'two\n'
        assert json.loads(attrs['gen_ai.tool.call.arguments']) == {'path': 'note.txt'}
        outcome = json.loads(attrs['gen_ai.tool.call.result'])
        assert outcome['terminal']['truncated'] is True
        assert outcome['terminal']['output'] == 'é' * 3
        assert outcome['terminal']['exitStatus']['exitCode'] == 0
    else:
        assert result.output == 'denied'
        assert not (tmp_path / 'note.txt').exists()
        assert attrs['abb.tool_arguments_omission'] == 'not_observed'
        assert 'gen_ai.tool.call.result' not in attrs
        assert tool['status']['status_code'] == 'ERROR'
    summary = json.loads((tmp_path / 'trace/acp-summary.json').read_text())
    assert summary['internal_model_spans'] == 'not_observed'
    assert summary['incomplete_tools'] == []
    assert json.loads((tmp_path / 'trace/otel-status.json').read_text())['status'] == 'complete'


def test_file_callbacks_reject_outside_and_symlink_escape(tmp_path):
    workspace = tmp_path / 'work'
    workspace.mkdir()
    config = ACPConfig(tmp_path, ('test',), str(workspace), max_output_bytes=1024)
    (workspace / 'escape').symlink_to(tmp_path, target_is_directory=True)
    for path in (tmp_path / 'outside', workspace / 'escape/outside'):
        with pytest.raises(Exception, match='Invalid params'):
            write_file(config, str(path), 'no')
    write_file(config, str(workspace / 'nested/file'), 'a\nb\n')
    assert read_file(config, str(workspace / 'nested/file'), 2, 1).content == 'b\n'
    with pytest.raises(Exception, match='Invalid params'):
        write_file(config, str(workspace / 'large'), 'x' * 1025)


def test_terminals_are_killed_and_released_with_session(tmp_path):
    async def run():
        config = ACPConfig(tmp_path, ('test',), str(tmp_path), cleanup_timeout=.2)
        terminals = Terminals(config, lambda *args: None)
        result = await terminals.create(sys.executable, ['-c', 'import time; time.sleep(60)'])
        process = terminals.items[result.terminal_id].process
        assert (await terminals.output(result.terminal_id)).exit_status is None
        await terminals.close()
        assert process.returncode is not None
        assert terminals.items == {}
    asyncio.run(run())

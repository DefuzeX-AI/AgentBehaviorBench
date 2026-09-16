"""Issue #20: preserve actual per-Input SDK evidence status through multi-turn runs."""
import asyncio
import json
from collections.abc import Mapping

import pytest

from agentbench.sdk.plugin.kuma.runner import drive_run
from agentbench.observe.invocation import InvocationObservation
from tests.sdk_fixtures.issue_run import sdk_run


@pytest.mark.parametrize('turns', [1, 2, 3, 5])
def test_sdk_multi_turn_history_and_capture_status(tmp_path, turns):
    inputs = ['Remember my code word: blue'] + ['Recall the code word'] * (turns-1)
    for case_index in range(2):
        delivered = []
        with sdk_run(tmp_path/f'repo-{case_index}', inputs) as (run, provider):
            async def invoke(payload, folder, shared_provider):
                delivered.append(payload)
                observed = InvocationObservation(folder, f'invoke-{len(delivered)}', run.run_id, 'langgraph', provider=shared_provider)
                observed.store.record('execution_start', input=payload)
                assert payload == inputs[len(delivered)-1]
                # The Agent's result is evidence, never input for the next turn.
                result = {'status': 'succeeded', 'output': f'answer-{len(delivered)}',
                          'raw_output': {'messages': [{'role': 'assistant', 'content': 'PRIVATE AGENT HISTORY'}]}}
                observed.store.record('execution_end', output=result['output'])
                observed.close()
                return result
            output = tmp_path/f'output-{case_index}'
            summary = asyncio.run(drive_run(run, invoke, output, provider=provider))
            assert summary['judge'] == 'received'
            # PyPI KUMA freezes Submission JSON into read-only mappings. A real
            # committed trace must still pass the worker's evidence gate.
            evidence = run.history[0].submission.extensions['trace_evidence']
            assert isinstance(evidence, Mapping) and not isinstance(evidence, dict)
            assert summary['evidence'] == 'captured'
            assert len(run.history) == turns
            assert delivered == inputs
            for i, payload in enumerate(inputs, 1):
                assert json.loads((output/f'inputs/{i:04d}/mapped-input.json').read_text()) == payload
                context = json.loads((output/f'inputs/{i:04d}/context.json').read_text())
                assert context['input_delivery'] == 'current_input'
                assert context['context_owner'] == 'agent'
                assert context['session_id'] == run.run_id
            for i, record in enumerate(run.history, 1):
                stored = json.loads((output/f'inputs/{i:04d}/capture-status.json').read_text())
                submission = json.loads((output/f'inputs/{i:04d}/submission.json').read_text())
                assert stored['capture_status'] == submission['capture_status']
                assert stored['capture_status']['traces']['status'] in ('complete', 'partial')
                assert stored['tool_content_status'] == []  # Root span is not invented tool evidence.
                assert stored['trace_summary'] == {
                    key: submission['extensions']['trace_evidence'].get(key)
                    for key in ('reasons', 'missing', 'dropped_count')}
                assert summary['steps'][i-1]['submission_status'] == 'completed'


@pytest.mark.parametrize('status,expected', [('timeout', 'timeout'), ('cancelled', 'aborted')])
def test_explicit_agent_terminal_status_reaches_sdk(tmp_path, status, expected):
    with sdk_run(tmp_path/'repo', ['task']) as (run, provider):
        async def invoke(payload, folder, shared_provider):
            observed = InvocationObservation(folder, 'invoke', run.run_id, 'langgraph', provider=shared_provider)
            observed.store.record('execution_start', input=payload)
            observed.store.record('execution_error', error='explicit terminal status')
            observed.close()
            return {'status': status, 'error': 'explicit terminal status'}
        summary = asyncio.run(drive_run(run, invoke, tmp_path/'output', provider=provider))
        assert run.history[0].submission.status == expected
        assert summary['execution'] == 'failed'

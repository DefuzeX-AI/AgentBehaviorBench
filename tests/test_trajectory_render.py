"""Rendering follows TraceElephant's full / truncate_middle / response_only modes."""
import json

import pytest

from agentbench.trajectory import build, validate
from agentbench.trajectory.render import render, render_step, render_within
from tests.trajectory_fixtures import langgraph_attempt


def test_full_mode_keeps_every_request_and_response(tmp_path):
    value = validate(build(langgraph_attempt(tmp_path)))
    text = render(value, 'full')
    assert text.startswith('Agent: alpha (langgraph)')
    assert 'Step 1 - alpha [model]:' in text and 'Step 2 - alpha [model]:' in text
    assert text.count('You are alpha.') == 2  # both requests carry the full history
    assert 'You are alpha.' in render_step(value['steps'][1], 'full')
    assert '"tool_logs"' in text and '"exit_status"' in text


def test_truncate_middle_only_shortens_long_requests(tmp_path):
    value = validate(build(langgraph_attempt(tmp_path)))
    value['steps'][0]['input']['messages'][1]['content'] = 'p' * 5000
    line = render_step(value['steps'][0], 'truncate_middle')
    assert '[TRUNCATED] ' in line and '...[truncated middle content]...' in line
    assert json.dumps(value['steps'][0]['output'], ensure_ascii=False) in line
    short = render_step(value['steps'][1], 'truncate_middle')
    assert '[TRUNCATED]' not in short


def test_response_only_drops_requests(tmp_path):
    value = validate(build(langgraph_attempt(tmp_path)))
    line = render_step(value['steps'][0], 'response_only')
    assert '"request"' not in line and '"response"' in line


def test_render_within_never_drops_inputs(tmp_path):
    value = validate(build(langgraph_attempt(tmp_path)))
    text, mode = render_within(value, 10 ** 6)
    assert mode == 'full'
    value['steps'][0]['input']['messages'][1]['content'] = 'p' * 5000
    text, mode = render_within(value, len(render(value, 'full').encode()) - 1)
    assert mode == 'truncate_middle'
    assert render_within(value, 100) == (None, None)


def test_unknown_mode_is_rejected(tmp_path):
    value = validate(build(langgraph_attempt(tmp_path)))
    with pytest.raises(ValueError):
        render_step(value['steps'][0], 'summary')

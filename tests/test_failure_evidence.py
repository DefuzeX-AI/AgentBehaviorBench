import json
from agentbench.observe.view_api import RunViewAPI
from agentbench.observe.failures import tool_failures

MESSAGE = "This request exceeds your plan's set usage limit. Please upgrade your plan."


def record(tmp_path, error=MESSAGE, tool='tavily.search'):
    folder = tmp_path / 'evaluation/inputs/0001'
    folder.mkdir(parents=True)
    rows = [
        {'event': 'span_start', 'data': {'span_id': 'a', 'kind': 'tool', 'name': tool}},
        {'event': 'span_error', 'data': {'span_id': 'a', 'error': error}},
        {'event': 'span_error', 'data': {'span_id': 'a', 'error': error}},
    ]
    (folder / 'framework.jsonl').write_text('\n'.join(map(json.dumps, rows))+'\n{', encoding='utf-8')
    return RunViewAPI(tmp_path)


def test_saved_tool_error_has_evidence_and_deduplicates(tmp_path):
    api = record(tmp_path)
    errors = api.evaluation()['inputs'][0]['failures']
    assert len(errors) == 1
    assert errors[0]['category'] == 'quota_exceeded'
    assert errors[0]['message'] == MESSAGE
    assert errors[0]['source'] == 'evaluation/inputs/0001/framework.jsonl:2'


def test_429_is_not_quota_exhaustion(tmp_path):
    api = record(tmp_path, {'code': '429', 'message': 'Too many requests'})
    assert tool_failures(api, 'evaluation/inputs/0001')[0]['category'] == 'tool_error'


def test_other_provider_does_not_use_tavily_rule(tmp_path):
    api = record(tmp_path, tool='other.search')
    assert tool_failures(api, 'evaluation/inputs/0001')[0]['category'] == 'tool_error'


def test_unknown_structured_code_takes_precedence_over_text(tmp_path):
    api = record(tmp_path, {'code': 'unknown', 'message': MESSAGE})
    assert tool_failures(api, 'evaluation/inputs/0001')[0]['category'] == 'tool_error'


def test_missing_trace_is_optional(tmp_path):
    assert tool_failures(RunViewAPI(tmp_path), 'evaluation/inputs/0001') == []

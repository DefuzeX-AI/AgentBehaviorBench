"""Code-only ACP units expose the valid empty tool-route array during SDK staging."""
import json
import pytest
from agentbench.sdk.common.whitelist import append_whitelist, tomllib


@pytest.mark.parametrize('declaration', ['tool_routes = []', '"tool_routes" = [\n# intentionally empty\n]', "'tool_routes'=[] # empty"])
def test_sdk_can_append_routes_to_empty_array_without_changing_other_tables(tmp_path, declaration):
    whitelist = tmp_path / 'whitelist.json'
    whitelist.write_text(json.dumps([{'url': 'https://sdk.example/api', 'methods': ['POST']}]))
    original = '[unrelated]\ntool_routes=[]\n[llm_interception]\nrequired=true\n' + declaration + '\n'
    result = tomllib.loads(append_whitelist(original, whitelist))
    assert result['unrelated']['tool_routes'] == []
    assert result['llm_interception']['required'] is True
    assert result['llm_interception']['tool_routes'][0]['purpose'] == 'evaluation'
    assert result['llm_interception']['tool_routes'][0]['host_patterns'] == ['sdk.example']

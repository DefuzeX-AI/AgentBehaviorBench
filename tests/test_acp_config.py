"""Static ACP configuration stays usable without process or network access."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from agentbench.adapter.factory import create_adapter
from agentbench.adapter.acp.config import ACPConfig


@pytest.mark.parametrize('field,value,reason', [
    ('command', 'mcode acp', 'array'),
    ('command', [], 'non-empty'),
    ('transport', 'http', 'stdio'),
    ('cwd', 'relative', 'absolute'),
    ('permission_policy', 'allow_always', 'allow_once'),
    ('handshake_timeout', -1, 'positive'),
    ('cleanup_timeout', True, 'positive'),
    ('max_output_bytes', 1, 'between'),
    ('mode', 'in_process', 'Unknown'),
])
def test_invalid_configuration_is_rejected_offline(tmp_path, field, value, reason):
    values = {'type': 'acp', 'command': ['mcode', 'acp'], 'cwd': '/workspace', field: value}
    content = '[adapter]\n' + '\n'.join(f'{k} = {json.dumps(v)}' for k, v in values.items())
    (tmp_path / 'agent.toml').write_text(content)
    with pytest.raises(ValueError, match=reason):
        ACPConfig.from_agent_dir(tmp_path)


def test_factory_constructs_acp_without_starting_it(tmp_path):
    (tmp_path / 'agent.toml').write_text('[adapter]\ntype="acp"\ncommand=["missing-binary"]\ncwd="/workspace"')
    adapter = create_adapter(SimpleNamespace(path=tmp_path, framework='acp'))
    assert not adapter.is_loaded
    assert adapter.config.command == ('missing-binary',)
    adapter.close()

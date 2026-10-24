from pathlib import Path
import importlib.util
import shutil
import pytest
from agentbench.adapter.acp.config import ACPConfig
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.runtime.interception.native_model import model_declaration
import tomllib
UNIT=Path(__file__).resolve().parents[1]/'resources/agents/82-openharness'
spec=importlib.util.spec_from_file_location('openharness_launcher',UNIT/'bootstrap/launch.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)

def test_missing_runtime_model_is_rejected():
    with pytest.raises(ValueError,match='ABB_AGENT_MODEL'):
        launcher.prepare({'DEEPSEEK_API_KEY':'unused'})

def test_credentials_are_not_serialized_and_homes_are_distinct():
    env={'ABB_AGENT_MODEL_API_KEY':'not-a-real-credential','ABB_AGENT_MODEL':'deepseek-chat','ABB_AGENT_MODEL_BASE_URL':'https://api.deepseek.com/v1','NODE_EXTRA_CA_CERTS':'/tmp/ca.pem'}
    homes=[]
    try:
        for _ in range(2):
            command,child=launcher.prepare(env);homes.append(child['HOME'])
            assert command[-1]=='openai/deepseek-chat'
            assert env['ABB_AGENT_MODEL_API_KEY'] not in str(command)
            assert child['OPENAI_API_KEY']==env['ABB_AGENT_MODEL_API_KEY']
            assert child['NODE_EXTRA_CA_CERTS']=='/tmp/ca.pem'
            assert env['ABB_AGENT_MODEL_API_KEY'] not in (Path(child['HOME'])/'.oh/config.yaml').read_text()
            assert Path(child['XDG_CONFIG_HOME']).is_relative_to(Path(child['HOME']))
        assert homes[0]!=homes[1]
    finally:
        for p in homes:shutil.rmtree(p)

def test_shared_model_configuration():
    manifest=tomllib.loads((UNIT/'agent.toml').read_text())
    assert model_declaration(manifest)[0]=='shared'
    assert manifest['model']['provider']=='deepseek'
    cfg=ACPConfig.from_agent_dir(UNIT)
    assert cfg.cwd==manifest['evaluation']['workspace']['path']
    assert 'ABB_AGENT_MODEL_API_KEY' in cfg.env_keys
    assert not InterceptionConfig.from_agent_dir(UNIT).routes
    assert manifest['source']['method']=='git'

def test_profile_official_parser():
    from kuma.repository.agent_profiles import parse_agent_profile
    assert parse_agent_profile(UNIT/'requirement.md').input_type=='text'

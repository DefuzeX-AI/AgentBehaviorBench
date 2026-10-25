"""Offline contract for Issue #482; no external model requests."""
from pathlib import Path
import os, json, tomllib, importlib.util, stat
import pytest
ROOT=Path(os.environ.get('ABB_UNIT_TEST_ROOT',Path(__file__).resolve().parents[1]));UNIT=ROOT/'resources/agents/110-microclaw'
def module():
    spec=importlib.util.spec_from_file_location('microclaw_abb_launch',UNIT/'bootstrap/launch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def env():return {'ABB_AGENT_MODEL':'fixture-model','ABB_AGENT_MODEL_BASE_URL':'https://fixture.example/v1','ABB_AGENT_MODEL_API_KEY':'fixture-credential'}
def test_unit_registration():
    c=tomllib.loads((UNIT/'agent.toml').read_text());assert c['framework']=='acp' and c['source']['method']=='install';assert c['source']['revision']=='45ad5e7a8c705080a94543c92319f81b7e0e884f';assert c['evaluation']['file_evidence']['track_files'];r=tomllib.loads((ROOT/'resources/registry.toml').read_text())['agents'];row=next(x for x in r if x['agent_id']=='microclaw');assert row['path']=='resources/agents/110-microclaw' and row['enabled'] is False and row['status']=='adapting'
def test_native_command_and_model():
    cmd,config=module().settings(env(),'/tmp/fixture-home');assert cmd==['/usr/local/bin/microclaw','acp'];assert config['model']=='fixture-model' and config['llm_base_url']=='https://fixture.example/v1' and config['api_key']=='fixture-credential';assert 'fixture-credential' not in json.dumps(cmd);assert config['working_dir_isolation']=='direct';assert config['working_dir']=='/home/agent/workspace';assert config['fallback_model'] is None and config['aux_models']=={x:'fixture-model' for x in ('compaction','reflector','title','vision')}
@pytest.mark.parametrize('key',['ABB_AGENT_MODEL','ABB_AGENT_MODEL_BASE_URL','ABB_AGENT_MODEL_API_KEY'])
def test_no_missing_fallback(key):
    e=env();e.pop(key)
    with pytest.raises(ValueError,match=key):module().settings(e,'/tmp/fixture-home')
@pytest.mark.parametrize('url',['http://fixture.example/v1','https://u:p@fixture.example/v1','https://fixture.example/v1?key=x','https://fixture.example/v1#x','file:///tmp/model','https://fixture.example/v1\n'])
def test_endpoint_validation(url):
    e=env();e['ABB_AGENT_MODEL_BASE_URL']=url
    with pytest.raises(ValueError):module().settings(e,'/tmp/fixture-home')
def test_private_config_and_isolation(tmp_path,monkeypatch):
    m=module();monkeypatch.setattr(m.tempfile,'gettempdir',lambda:str(tmp_path));e={**env(),'HOME':'/prior','MICROCLAW_CONFIG':'/prior/settings','MICROCLAW_GATEWAY':'1'};cmd,child,home=m.prepare(e);config=Path(child['MICROCLAW_CONFIG']);assert home!=Path('/prior');assert config.is_relative_to(home);assert stat.S_IMODE(config.stat().st_mode)==0o600;assert stat.S_IMODE(home.stat().st_mode)==0o700;assert json.loads(config.read_text())['model']=='fixture-model';assert child['MICROCLAW_GATEWAY']=='1';assert e['HOME']=='/prior';assert child['HOME']==str(home)
def test_recipe_and_profile():
    d=(UNIT/'Dockerfile').read_text();assert 'USER agent' in d and 'COPY .abb-runtime/' in d;assert 'install_native.py' in d and 'cargo build' not in d;assert 'COPY agent/' in d;assert (UNIT/'ground_truth/.gitkeep').is_file();profile=(UNIT/'requirement.md').read_text();assert 'input_type: text' in profile and 'does not emit native ACP tool-call notifications' in profile

def test_install_descriptor_and_native_defaults():
    c=tomllib.loads((UNIT/'agent.toml').read_text());assert c['build']['context']=='.'
    d=json.loads((UNIT/'install/abb-native-release.json').read_text());assert d['revision']==c['source']['revision'] and d['version']=='0.10.1';assert set(d['artifacts'])=={'aarch64','x86_64'}
    for a in d['artifacts'].values():
        assert a['url'].startswith('https://github.com/microclaw/microclaw/releases/download/v0.10.1/') and len(a['sha256'])==64
    _,settings=module().settings(env(),'/tmp/fixture-home');assert 'high_risk_tool_user_confirmation_required' not in settings and 'tools' not in settings

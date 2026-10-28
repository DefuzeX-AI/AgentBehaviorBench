from pathlib import Path
import importlib.util,json,subprocess,sys,time
import pytest
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'resources/agents/139-openaeon/bootstrap/launch.py'
spec=importlib.util.spec_from_file_location('openaeon_candidate',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ENV={'ABB_AGENT_MODEL':'glm-5.3-flash','ABB_AGENT_MODEL_BASE_URL':'https://model.example.test/v1','ABB_AGENT_MODEL_API_KEY':'synthetic-fixture-only'}
@pytest.mark.parametrize('key',list(ENV))
def test_missing_route_fails_closed(tmp_path,key):
 env={**ENV};env.pop(key)
 with pytest.raises(ValueError,match='is required'):m.prepare(env,tmp_path/'home',tmp_path)
@pytest.mark.parametrize('url',['http://example.test','https://user:secret@example.test','https://example.test?q=x','https://example.test#fragment','https://example.test/a b'])
def test_invalid_route_not_echoed(tmp_path,url):
 with pytest.raises(ValueError) as e:m.prepare({**ENV,'ABB_AGENT_MODEL_BASE_URL':url},tmp_path/'home',tmp_path)
 assert url not in str(e.value)
def test_native_commands_private_route_no_fallback(tmp_path):
 env={**ENV,'OPENAI_API_KEY':'unused','OPENAEON_CONFIG_PATH':'untrusted','OPENCLAW_HOME':'untrusted','NODE_EXTRA_CA_CERTS':'/path/to/abb.pem'}
 g,a,e,port=m.prepare(env,tmp_path/'home',tmp_path)
 cfg=json.loads(Path(e['OPENAEON_CONFIG_PATH']).read_text());d=cfg['agents']['defaults'];selected='abb/glm-5.3-flash'
 assert g[:3]==['node','/opt/agent/agent/openaeon.mjs','gateway'] and a[:3]==['node','/opt/agent/agent/openaeon.mjs','acp']
 assert 'ws://127.0.0.1:'+str(port) in a and '--token-file' in a
 assert cfg['gateway']['bind']=='loopback' and cfg['gateway']['auth']['mode']=='token'
 assert cfg['models']['mode']=='replace' and list(cfg['models']['providers'])==['abb']
 assert cfg['models']['providers']['abb']['apiKey']=='${ABB_AGENT_MODEL_API_KEY}'
 assert d['model']==d['imageModel']==d['subagents']['model']=={'primary':selected,'fallbacks':[]}
 assert d['heartbeat']=={'every':'0m','model':selected}
 assert 'tools' not in cfg and 'skipBootstrap' not in d and 'systemPrompt' not in d
 assert 'OPENAI_API_KEY' not in e and 'OPENCLAW_HOME' not in e and e['NODE_EXTRA_CA_CERTS']=='/path/to/abb.pem'
 assert Path(e['OPENAEON_CONFIG_PATH']).stat().st_mode&0o777==0o600
 assert Path(a[a.index('--token-file')+1]).stat().st_mode&0o777==0o600
 assert 'synthetic-fixture-only' not in Path(e['OPENAEON_CONFIG_PATH']).read_text()
def test_case_states_are_isolated(tmp_path):
 x=m.prepare(ENV,tmp_path/'one',tmp_path);y=m.prepare(ENV,tmp_path/'two',tmp_path)
 assert x[2]['OPENAEON_CONFIG_PATH']!=y[2]['OPENAEON_CONFIG_PATH']
 assert x[2]['OPENAEON_GATEWAY_TOKEN']!=y[2]['OPENAEON_GATEWAY_TOKEN']
def test_preserve_existing_state(tmp_path):
 m.prepare(ENV,tmp_path/'one',tmp_path)
 with pytest.raises(FileExistsError):m.prepare(ENV,tmp_path/'one',tmp_path)
def test_owned_real_process_cleanup():
 p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
 try:m.stop(p);assert p.poll() is not None
 finally:
  if p.poll() is None:p.kill();p.wait()
def test_startup_failure_is_explicit():
 class P:
  def poll(self):return 1
 with pytest.raises(RuntimeError,match='before accepting'):m.wait_gateway(P(),9,timeout=0.2)
def test_startup_timeout_is_bounded():
 class P:
  def poll(self):return None
 with pytest.raises(TimeoutError):m.wait_gateway(P(),9,timeout=0.01)


def test_bundled_manifest_has_no_provider_pin_and_native_source_is_not_tracked():
    import tomllib
    root=P.parents[1]
    config=tomllib.loads((root/'agent.toml').read_text())
    assert config['source']['method']=='bundled'
    assert config['source']['revision']=='e9b35678fbacc9a2c018574b6731202228f8686d'
    assert 'model' not in config
    assert config['adapter']['type']=='acp'
    assert config['adapter']['command']==['python','/opt/agent/bootstrap/launch.py']
    assert config['evaluation']['workspace']['path']=='/workspace/project'


def test_manual_preparer_preserves_original_files_and_links(tmp_path,monkeypatch):
    import hashlib
    unit=tmp_path/'unit';unit.mkdir();source=tmp_path/'source';source.mkdir()
    (source/'native.ts').write_text('original source\n');(source/'alias').symlink_to('native.ts')
    hashes={'native.ts':hashlib.sha256((source/'native.ts').read_bytes()).hexdigest(),'alias':hashlib.sha256(b'native.ts').hexdigest()}
    (unit/'source-file-sha256.json').write_text(json.dumps(hashes))
    spec=importlib.util.spec_from_file_location('openaeon_preparer',P.parent/'prepare_source.py');preparer=importlib.util.module_from_spec(spec);spec.loader.exec_module(preparer)
    monkeypatch.setattr(preparer,'UNIT',unit);monkeypatch.setattr(sys,'argv',['prepare_source.py',str(source)])
    preparer.main();assert (unit/'agent/native.ts').read_bytes()==(source/'native.ts').read_bytes()
    assert (unit/'agent/alias').is_symlink() and (unit/'agent/alias').readlink()==Path('native.ts')
    with pytest.raises(SystemExit):preparer.main()


def test_manual_preparer_rejects_changed_native_bytes_before_copy(tmp_path,monkeypatch):
    unit=tmp_path/'unit';unit.mkdir();source=tmp_path/'source';source.mkdir();(source/'native.ts').write_text('changed')
    (unit/'source-file-sha256.json').write_text(json.dumps({'native.ts':'0'*64}))
    spec=importlib.util.spec_from_file_location('openaeon_bad_preparer',P.parent/'prepare_source.py');preparer=importlib.util.module_from_spec(spec);spec.loader.exec_module(preparer)
    monkeypatch.setattr(preparer,'UNIT',unit);monkeypatch.setattr(sys,'argv',['prepare_source.py',str(source)])
    with pytest.raises(AssertionError,match='Pinned source hash'):preparer.main()
    assert not (unit/'agent').exists()


def test_public_compile_cache_is_copied_into_private_case_state(tmp_path):
    seed=tmp_path/'public-cache';seed.mkdir();(seed/'compiled').write_bytes(b'public-bytecode-fixture')
    _,_,env,_=m.prepare(ENV,tmp_path/'home',tmp_path,compile_cache=seed)
    private=Path(env['NODE_COMPILE_CACHE']);assert private.is_relative_to(tmp_path/'home')
    assert (private/'compiled').read_bytes()==b'public-bytecode-fixture'
    (private/'compiled').write_bytes(b'case-local-change')
    assert (seed/'compiled').read_bytes()==b'public-bytecode-fixture'


def test_manifest_keeps_bounded_startup_and_native_node_cache():
    import inspect,tomllib
    unit=P.parents[1];config=tomllib.loads((unit/'agent.toml').read_text())
    assert config['adapter']['handshake_timeout']==300
    assert config['runtime']['timeout_sec']==900
    assert inspect.signature(m.wait_gateway).parameters['timeout'].default==180
    recipe=(unit/'Dockerfile').read_text();assert 'cp -a /tmp/node-compile-cache/.' in recipe
    assert 'chmod -R a+rX /opt/openaeon-node-cache /opt/openaeon-jiti-cache' in recipe


def test_native_jiti_cache_is_case_private_and_seed_unchanged(tmp_path):
    seed=tmp_path/'public-jiti';seed.mkdir();(seed/'plugin.cjs').write_text('original-transformed-module')
    _,_,env,_=m.prepare(ENV,tmp_path/'home',tmp_path,jiti_cache=seed)
    assert env['JITI_FS_CACHE']=='true'
    private=Path(env['TMPDIR'])/'jiti';assert private.is_relative_to(tmp_path/'home')
    assert (private/'plugin.cjs').read_text()=='original-transformed-module'
    (private/'plugin.cjs').write_text('case-local-write')
    assert (seed/'plugin.cjs').read_text()=='original-transformed-module'


def test_bridge_selects_an_isolated_native_main_session_not_external_acp(tmp_path):
    _,a,_,_=m.prepare(ENV,tmp_path/'one',tmp_path)
    assert '--session' in a
    session=a[a.index('--session')+1]
    assert session.startswith('agent:main:abb-')
    assert ':acp:' not in session and not session.startswith('acp:')
    _,b,_,_=m.prepare(ENV,tmp_path/'two',tmp_path)
    assert b[b.index('--session')+1]!=session


def test_native_stderr_tee_preserves_exact_bytes(tmp_path,monkeypatch):
    import os,io,types
    payload='[acp] newSession: original -> agent:main:abb-0123456789abcdef\nUTF8: \u539f\u6587\n'.encode()
    read_fd,write_fd=os.pipe();os.write(write_fd,payload);os.close(write_fd)
    forwarded=io.BytesIO();monkeypatch.setattr(m.sys,'stderr',types.SimpleNamespace(buffer=forwarded))
    with os.fdopen(read_fd,'rb') as stream:m.tee_native_stderr(stream,tmp_path/'native.log')
    assert (tmp_path/'native.log').read_bytes()==payload and forwarded.getvalue()==payload


def test_two_stubborn_native_groups_stop_within_default_acp_budget():
    import os,signal
    children=[]
    try:
        for _ in range(2):
            child=subprocess.Popen([sys.executable,'-u','-c',
                'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(60)'],
                stdout=subprocess.PIPE,text=True,start_new_session=True)
            children.append(child);assert child.stdout.readline().strip()=='ready'
        started=time.monotonic();m.stop_many(*children)
        assert time.monotonic()-started<2.8
        assert all(child.returncode==-signal.SIGKILL for child in children)
        for child in children:
            with pytest.raises(ProcessLookupError):os.killpg(child.pid,0)
    finally:
        for child in children:
            if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait()


def test_registry_keeps_a_unique_numeric_directory_prefix():
    import tomllib
    rows=tomllib.loads((ROOT/'resources/registry.toml').read_text())['agents']
    selected=next(r for r in rows if r['agent_id']=='openaeon')
    assert (ROOT/selected['path']).resolve()==P.parents[1].resolve()
    prefix=Path(selected['path']).name.split('-',1)[0]
    assert [r['agent_id'] for r in rows if Path(r['path']).name.split('-',1)[0]==prefix]==['openaeon']

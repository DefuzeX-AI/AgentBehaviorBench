"""No-credential boundary, source-preservation and real subprocess regressions."""
from pathlib import Path
import importlib.util
import json
import struct
import hashlib
from types import SimpleNamespace
import pytest

UNIT=Path(__file__).resolve().parents[1]/'resources/agents/63-decompai'
def module(name,file):
 s=importlib.util.spec_from_file_location(name,UNIT/'bindings'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
bridge=module('issue375_bridge','bridge.py')
transport=module('issue375_transport','container_transport.py')

def elf(path,machine=62):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'\x7fELF\x02\x01'+b'\x00'*12+struct.pack('<H',machine));return path

@pytest.mark.parametrize('value',['',None,12,[],{}])
def test_bad_request_is_explicit(value):
 with pytest.raises((ValueError,TypeError)):bridge.parse_input(value)

def test_default_fixture_and_text(monkeypatch,tmp_path):
 monkeypatch.setattr(bridge,'UNIT',tmp_path);p=elf(tmp_path/'fixtures/branch')
 assert bridge.parse_input({'request':'explain branch'})==('explain branch',p)
 assert bridge.parse_input('explain branch')==('explain branch',p)

def test_json_path_and_instruction(monkeypatch,tmp_path):
 monkeypatch.setattr(bridge,'UNIT',tmp_path);p=elf(tmp_path/'fixtures/sample')
 assert bridge.parse_input(json.dumps({'instruction':'inspect','binary_path':str(p)}))==('inspect',p)
 assert bridge.parse_input({'request':'inspect','binary_path':str(p)})==('inspect',p)

def test_external_binary_rejected(monkeypatch,tmp_path):
 monkeypatch.setattr(bridge,'UNIT',tmp_path/'unit');p=elf(tmp_path/'outside')
 with pytest.raises(ValueError,match='fixture or'):bridge.parse_input({'request':{'request':'inspect','binary_path':str(p)}})

@pytest.mark.parametrize('machine',[40,183])
def test_non_x86_elf_rejected(monkeypatch,tmp_path,machine):
 monkeypatch.setattr(bridge,'UNIT',tmp_path);p=elf(tmp_path/'fixtures/sample',machine)
 with pytest.raises(ValueError,match='x86'):bridge.parse_input(json.dumps({'request':'inspect','binary_path':str(p)}))

def test_not_elf_rejected(monkeypatch,tmp_path):
 monkeypatch.setattr(bridge,'UNIT',tmp_path);p=tmp_path/'fixtures/branch';p.parent.mkdir();p.write_text('hello')
 with pytest.raises(ValueError,match='ELF'):bridge.parse_input('inspect')

def test_native_prompt_is_literal_source(monkeypatch,tmp_path):
 source=tmp_path/'src/main.py';source.parent.mkdir(parents=True)
 prompt='Native literal prompt; do not paraphrase.'
 source.write_text('def start_session():\n    system_prompt = '+repr(prompt)+'\n')
 monkeypatch.setattr(bridge,'SOURCE',tmp_path)
 assert bridge.upstream_system_prompt()==prompt

def test_provenance_is_pinned_without_local_source():
 data=json.loads((UNIT/'source-provenance.json').read_text())
 assert len(data['regular_file_sha256'])==31
 assert all(len(h)==64 for h in data['regular_file_sha256'].values())

def test_native_regular_files_are_byte_identical():
 if not (UNIT/'agent/src/main.py').is_file():
  pytest.skip('Optional source-preservation integration check: run prepare_source.py first')
 for path,h in json.loads((UNIT/'source-provenance.json').read_text())['regular_file_sha256'].items():
  assert hashlib.sha256((UNIT/'agent'/path).read_bytes()).hexdigest()==h
 assert (UNIT/'agent/decompai_analysis_sessions').is_dir()
 assert not any(p.is_symlink() for p in (UNIT/'agent').rglob('*'))

def test_native_runtime_is_not_executed_on_host():
 if bridge.sys.platform!='linux':
  with pytest.raises(RuntimeError,match='ABB'):bridge._native()

def test_transport_real_stdout_stderr(tmp_path):
 p=transport.ContainerBashProcess(workdir=str(tmp_path));out=p.run("printf 'stdout'; printf 'stderr' >&2; exit 3")
 assert out=='stdout\n=== STDERR ===\nstderr'
 transport.close_all()

def test_transport_persistent_state_and_cleanup(tmp_path):
 p=transport.ContainerBashProcess(persistent=True,workdir=str(tmp_path))
 try:
  p.run('export ABB_TEST_VALUE=preserved; mkdir sub; cd sub')
  out=p.run('printf "%s:%s" "$ABB_TEST_VALUE" "${PWD##*/}"')
  assert 'preserved:sub' in out
 finally:transport.close_all()
 assert p.process is None

def test_transport_reused_object_is_closed(tmp_path):
 p=transport.ContainerBashProcess(persistent=True,workdir=str(tmp_path));p.run('printf first');transport.close_all()
 assert 'second' in p.run('printf second');transport.close_all();assert p.process is None

def test_transport_timeout_is_explicit(monkeypatch,tmp_path):
 monkeypatch.setenv('DECOMPAI_TOOL_TIMEOUT','1');p=transport.ContainerBashProcess(persistent=True,workdir=str(tmp_path))
 with pytest.raises(TimeoutError):p.run('sleep 3')
 assert p.process is None;transport.close_all()

def test_transport_does_not_spawn_docker(tmp_path,monkeypatch):
 original=transport.subprocess.run;args=[]
 def run(argv,**kw):args.append(argv);return original(argv,**kw)
 monkeypatch.setattr(transport.subprocess,'run',run)
 p=transport.ContainerBashProcess(workdir=str(tmp_path));assert 'actual' in p.run('printf actual')
 assert args==[['/bin/bash','-c','printf actual']];transport.close_all()

def test_utility_result_keeps_real_stderr():
 class Result:
  def __init__(self,stdout,stderr,combined):self.stdout=stdout;self.stderr=stderr;self.combined=combined
 fake=SimpleNamespace(CommandResult=Result);shell=SimpleNamespace();transport.install(fake,shell)
 r=fake.run_command_in_docker('printf real; printf failure >&2; exit 9')
 assert r.stdout=='real' and r.stderr=='failure' and 'STDERR' in r.combined
 assert shell.DockerizedBashProcess is transport.ContainerBashProcess

def test_factory_is_synchronous_without_importing_native():
 import inspect
 assert not inspect.iscoroutinefunction(bridge.create_graph)
 assert callable(bridge.create_graph().invoke) and callable(bridge.create_graph().ainvoke)

@pytest.mark.parametrize('mode',['success','over_budget','truncated','unfinished'])
def test_native_output_and_sticky_budget(monkeypatch,tmp_path,mode):
 from langchain_core.messages import AIMessage
 monkeypatch.syspath_prepend(str(UNIT/'bindings'))
 monkeypatch.setattr(bridge,'parse_input',lambda x:('inspect',tmp_path/'binary'))
 monkeypatch.setattr(bridge,'upstream_system_prompt',lambda:'native literal prompt')
 monkeypatch.setenv('DECOMPAI_MAX_CALLS','2')
 recorded={}
 class Graph:
  async def ainvoke(self,state,config,**kw):
   recorded['state']=state;recorded['config']=config;budget=config['callbacks'][-1]
   count=3 if mode=='over_budget' else 1
   for _ in range(count):
    try:budget.on_chat_model_start(None,None)
    except RuntimeError:pass # a native error handler must not turn exhaustion into success
   if mode=='truncated':
    budget.on_llm_end(SimpleNamespace(generations=[[SimpleNamespace(message=AIMessage(content='cut',response_metadata={'finish_reason':'length'}))]]))
   if mode=='unfinished':return {'messages':[]}
   return {'messages':[AIMessage(content='unaltered native answer')]}
 native=SimpleNamespace(utils=SimpleNamespace(create_session_for_binary=lambda p:str(tmp_path)),graph=Graph(),model_context_length=128000)
 monkeypatch.setattr(bridge,'_native',lambda:native)
 if mode=='success':
  out=bridge.create_graph().invoke('request',config={'configurable':{'custom':'kept'},'recursion_limit':8})
  assert out['answer']=='unaltered native answer' and out['model_calls']==1
  assert recorded['config']['recursion_limit']==8 and recorded['config']['configurable']['custom']=='kept'
  assert recorded['state']['messages'][0].content=='native literal prompt'
 else:
  with pytest.raises(RuntimeError):bridge.create_graph().invoke('request')

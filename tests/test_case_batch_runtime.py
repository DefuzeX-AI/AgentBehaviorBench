"""Batch preparation must happen once, before independent Case execution."""
from dataclasses import replace
import json
from types import SimpleNamespace
import pytest
from agentbench.sdk.kuma_runtime import benchmark
from agentbench.harness.result import BenchmarkResult
from agentbench.harness.runner.suite_runner import SuiteRunner


@pytest.fixture
def batch_runtime(monkeypatch, tmp_path):
    calls=[]
    faults={}
    runner=benchmark.KumaContainerRunner(options={'max_steps': 6, 'output': tmp_path})
    monkeypatch.setattr(runner, 'validate_sdk', lambda _: 'official-container')
    def evaluate(registration, **kwargs):
        calls.append(kwargs)
        folder=tmp_path / str(len(calls))
        (folder / 'evaluation').mkdir(parents=True)
        (folder / 'run.json').write_text(json.dumps({'status':'succeeded'}))
        if 'generation_count' in kwargs:
            count=kwargs['generation_count'] + faults.get('count_delta', 0)
            cases=[{'case_id':f'case-{i}', 'steps':[{'step_id':'step-1',
                'prompt':f'Research subject {0 if faults.get("duplicate") else i}'}]} for i in range(count)]
            (folder / 'evaluation/case-collection.json').write_text(json.dumps({
                'batches':[{'cases':cases}], 'entries':[{'batch_index':0,'case_index':i} for i in range(count)]}))
        else:
            raw=kwargs['case_batch']['cases'][kwargs['case_index']]
            (folder / 'evaluation/case.json').write_text(json.dumps({'case_id':raw['case_id'],
                'inputs':[{'payload_type':'text','payload':s['prompt']} for s in raw['steps']]}))
        return folder
    monkeypatch.setattr(benchmark,'evaluate',evaluate)
    monkeypatch.setattr(benchmark,'read_result',lambda directory, agent_id, *args: BenchmarkResult(
        agent_id, 'fixture', directory.name, 'report_ready', SimpleNamespace(status='pass'), (), 1))
    return runner,calls,faults


@pytest.mark.parametrize('count',[1,2,10])
def test_registry_count_becomes_one_batch_and_n_independent_executions(batch_runtime, starter_agent, count):
    runner,calls,_=batch_runtime
    result=SuiteRunner(benchmark_runner=runner).run([replace(starter_agent,case_count=count)])
    assert result.passed and result.items[0].completed_case_count==count
    generations=[c for c in calls if 'generation_count' in c]
    executions=[c for c in calls if 'case_index' in c]
    assert len(generations)==1 and generations[0]['generation_count']==count
    assert [c['case_index'] for c in executions]==list(range(count))
    assert all(c['max_steps']==6 for c in calls)
    assert len({c['case_batch']['cases'][c['case_index']]['steps'][0]['prompt'] for c in executions})==count
    # New suite generates once again, never reuses the previous batch.
    SuiteRunner(benchmark_runner=runner).run([replace(starter_agent,case_count=count)])
    assert len([c for c in calls if 'generation_count' in c])==2


@pytest.mark.parametrize('fault', ['duplicate','short','long'])
def test_invalid_batch_stops_before_any_agent_execution(batch_runtime, starter_agent, fault):
    runner,calls,faults=batch_runtime
    faults.update({'duplicate':True} if fault=='duplicate' else {'count_delta':-1 if fault=='short' else 1})
    result=SuiteRunner(benchmark_runner=runner).run([replace(starter_agent,case_count=2)])
    assert not result.passed and result.items[0].completed_case_count==0
    assert len(calls)==1 and calls[0]['generation_count']==2


def test_fallback_collects_ten_before_return_and_preserves_batch_identity(tmp_path):
    from agentbench.sdk.kuma_runtime.generation import generate_collection
    from agentbench.evaluation.artifacts import Artifacts
    calls=[]
    def generate(*, count):
        calls.append(count)
        if len(calls)==1:
            error=RuntimeError('batch unsupported')
            error.code='case_batch_unsupported'
            raise error
        assert count==1
        identifier=f'batch-{len(calls)}'
        return {'batch':{'batch_id':identifier},'cases':[{'case_id':f'case-{len(calls)}'}]}
    collection=generate_collection(generate,count=10,options={},files=Artifacts(tmp_path))
    assert calls==[10]+[1]*10
    assert collection['mode']=='single_fallback' and len(collection['entries'])==10
    assert len({b['batch']['batch_id'] for b in collection['batches']})==10
    assert [e['batch_index'] for e in collection['entries']]==list(range(10))
    assert all(e['case_index']==0 for e in collection['entries'])


@pytest.mark.parametrize('code',['invalid_request','model_timeout','quota_exhausted','invalid_response'])
def test_fallback_is_not_a_general_error_retry(tmp_path,code):
    from agentbench.sdk.kuma_runtime.generation import generate_collection
    from agentbench.evaluation.artifacts import Artifacts
    calls=[]
    def generate(**kw):
        calls.append(kw)
        error=RuntimeError('failed');error.code=code
        raise error
    with pytest.raises(RuntimeError):
        generate_collection(generate,count=2,options={},files=Artifacts(tmp_path))
    assert len(calls)==1


def test_fallback_failure_keeps_collected_cases_without_claiming_completion(tmp_path):
    from agentbench.sdk.kuma_runtime.generation import generate_collection
    from agentbench.evaluation.artifacts import Artifacts
    calls=[]
    def generate(*,count):
        calls.append(count)
        if len(calls)==1:
            error=RuntimeError('unsupported');error.code='case_batch_unsupported';raise error
        if len(calls)==3:
            raise RuntimeError('generation failed')
        return {'cases':[{'case_id':'first'}]}
    with pytest.raises(RuntimeError,match='generation failed'):
        generate_collection(generate,count=2,options={},files=Artifacts(tmp_path))
    saved=json.loads((tmp_path/'case-collection.json').read_text())
    assert len(saved['entries'])==1 and saved['requested_count']==2
    assert calls==[2,1,1]


def test_saved_collection_import_does_not_generate(batch_runtime, starter_agent, tmp_path):
    runner,calls,_=batch_runtime
    saved=tmp_path/'saved.json'
    saved.write_text(json.dumps({'batches':[
        {'cases':[{'case_id':f'case-{i}','steps':[{'prompt':f'Task {i}'}]}]} for i in range(2)],
        'entries':[{'batch_index':i,'case_index':0} for i in range(2)]}))
    runner.case_collection=saved
    original=saved.read_bytes()
    result=SuiteRunner(benchmark_runner=runner).run([replace(starter_agent,case_count=2)])
    assert result.passed
    assert len(calls)==2 and all('generation_count' not in c for c in calls)
    assert [c['case_batch']['cases'][0]['case_id'] for c in calls]==['case-0','case-1']
    assert saved.read_bytes()==original


@pytest.mark.parametrize('generation_count',[None,2])
def test_only_agent_execution_requires_a_model_trace(monkeypatch,tmp_path,generation_count):
    from contextlib import contextmanager
    from agentbench.sdk.kuma_runtime import service
    root=tmp_path/'unit';(root/'agent').mkdir(parents=True)
    agent=SimpleNamespace(path=root,agent_id='a')
    @contextmanager
    def overlay(*args):
        yield agent
    checked=[]
    session=SimpleNamespace(trace_checkpoint=lambda:None, wait=lambda **kw:0,
        validate_trace=lambda checkpoint:checked.append(checkpoint),close=lambda:None,
        stdout='',stderr='')
    monkeypatch.setattr(service,'evaluation_agent',overlay)
    monkeypatch.setattr(service,'DockerRuntime',lambda **kw:SimpleNamespace(start=lambda *a,**kw:session))
    output=service.evaluate(agent,output=tmp_path/'out',sdk=tmp_path,
        environ={'DEFUZEX_API_KEY':'fixture'},generation_count=generation_count)
    assert json.loads((output/'run.json').read_text())['status']=='succeeded'
    assert len(checked)==(1 if generation_count is None else 0)


@pytest.mark.parametrize('fault', ['negative_batch','negative_case','bool_index','missing_prompt','wrong_count'])
def test_invalid_saved_selection_rejected_before_execution(batch_runtime, starter_agent, tmp_path, fault):
    runner,calls,_=batch_runtime
    collection={'requested_count':1,'batches':[{'cases':[{'case_id':'a','steps':[{'prompt':'Question'}]}]}],
                'entries':[{'batch_index':0,'case_index':0}]}
    if fault=='negative_batch':collection['entries'][0]['batch_index']=-1
    elif fault=='negative_case':collection['entries'][0]['case_index']=-1
    elif fault=='bool_index':collection['entries'][0]['case_index']=False
    elif fault=='missing_prompt':collection['batches'][0]['cases'][0]['steps']=[{}]
    else:collection['requested_count']=2
    path=tmp_path/'invalid.json';path.write_text(json.dumps(collection));runner.case_collection=path
    result=SuiteRunner(benchmark_runner=runner).run([replace(starter_agent,case_count=1)])
    assert not result.passed and not calls
    rejected=list(tmp_path.glob('*/evaluation/batch-selection.json'))
    assert len(rejected)==1 and json.loads(rejected[0].read_text())['status']=='rejected'

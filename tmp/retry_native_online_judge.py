import json, os, sys
from pathlib import Path
from dataclasses import replace
sys.path.insert(0, str(Path.cwd()))
from agentbench.cli.environment import load_project_environment
from agentbench.harness.session import SuiteStore
from agentbench.harness.session.codec import case_from_json
from agentbench.harness.result import SuiteAgentResult, BenchmarkSuiteResult
from agentbench.cli.sessions.log import SuiteResultLog
from agentbench.sdk.contracts import SDKRunnerContext
from agentbench.sdk.judgment import DeferredJudgment
from agentbench.sdk.plugin.native.plugin import plugin
from kuma import list_requests
load_project_environment(None)
root = Path('C:/Song_startup/benchmark/r/suites/suite_3bc59c41bd89447990480bc9c3afe70b')
attempt = root/'cases/19fbeebdd093320f8b59c943/0/attempts/fded64d55eb64df391c0b1b95041baaf'
assert not list_requests(attempt/'judge-state'), 'Reconcile existing server request before retrying'
delivery = attempt/'evaluation/judge/delivery.json'
assert json.loads(delivery.read_bytes())['status'] == 'failed'
archive = delivery.with_name('delivery-before-runtime-envelope-fix.json')
assert not archive.exists()
delivery.rename(archive)
with SuiteStore.open(root, environ=dict(os.environ)) as store:
    row = store.snapshot()['jobs'][0]['cases'][0]
    prior = case_from_json(row['result'])
    agent = store.registrations[0]
    case = store.prepared_case(agent.agent_id, 0)
    context = SDKRunnerContext(environ=dict(os.environ), model=None, trace_sink=None, trace_max_bytes=262144)
    runner = plugin.create_benchmark_runner(context=context, options={'judge':'kuma'})
    store.append({'event':'progress','agent_id':agent.agent_id,'case_index':0,'attempt_id':prior.attempt_id,
                  'stage':'judge','status':'started','detail':'Retry Judge only after local runtime-envelope validation failure; Agent evidence unchanged'})
    result = runner.judge_case(agent, case, DeferredJudgment(attempt))
    final = replace(prior, status='succeeded' if result.passed else 'failed', benchmark=result,
                    error_type=None,error_message=None,artifacts={'directory':str(attempt)})
    item = SuiteAgentResult(agent.agent_id,(final,),1)
    writer = SuiteResultLog(store)
    writer.append_partial_results((item,))
    writer.append_suite_complete(BenchmarkSuiteResult(store.suite_id,(agent.agent_id,),(item,)))
    print('JUDGE_RESULT',result.report.status,flush=True)
    print('ISSUES',json.dumps(result.report.issues,ensure_ascii=False),flush=True)

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

load_project_environment(None)
root = Path('C:/Song_startup/benchmark/g/suites/suite_045b0373fc794789bd4c08b6aae1692b')
attempt = next(root.glob('cases/*/0/attempts/*'))
archive = attempt/'evaluation/judge/assessment-before-raw-retry'
archive.mkdir()
for name in ('delivery.json', 'report.json'):
    path = attempt/'evaluation/judge'/name
    if path.exists():
        path.rename(archive/name)
os.environ['ABB_LOCAL_JUDGE_MAX_CHARS'] = '240000'
with SuiteStore.open(root, environ=dict(os.environ)) as store:
    row = store.snapshot()['jobs'][0]['cases'][0]
    prior = case_from_json(row['result'])
    agent = store.registrations[0]
    case = store.prepared_case(agent.agent_id, 0)
    context = SDKRunnerContext(environ=dict(os.environ), model=None, trace_sink=None, trace_max_bytes=262144)
    runner = plugin.create_benchmark_runner(context=context, options={'judge':'local'})
    store.append({'event':'progress','agent_id':agent.agent_id,'case_index':0,'attempt_id':prior.attempt_id,
                  'stage':'judge','status':'started','detail':'User-requested Judge retry with raw response retention; prior failure archived; Agent evidence unchanged'})
    result = runner.judge_case(agent, case, DeferredJudgment(attempt))
    final = replace(prior, status='succeeded' if result.passed else 'failed', benchmark=result,
                    error_type=None,error_message=None,artifacts={'directory':str(attempt)})
    item = SuiteAgentResult(agent.agent_id,(final,),1)
    writer = SuiteResultLog(store)
    writer.append_partial_results((item,))
    writer.append_suite_complete(BenchmarkSuiteResult(store.suite_id,(agent.agent_id,),(item,)))
    print('JUDGE_RESULT',result.report.status,flush=True)
    print('ISSUES',json.dumps(result.report.issues,ensure_ascii=False),flush=True)

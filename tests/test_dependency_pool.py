"""Dependency cooldown releases execution slots for unrelated Agents."""
from dataclasses import replace
from agentbench.harness import SuiteRunner
from agentbench.harness.scheduling import RetryPolicy
from tests.test_suite_concurrency import Factory, agents, result


def test_dependency_cooldown_runs_other_agent_before_next_case():
    order, events = [], []
    def action(agent, case, *_):
        order.append((agent.agent_id, case.case_index))
        value = result(agent, case.case_index)
        if agent.agent_id == 'agent-0' and case.case_index == 0:
            return replace(value, dependency_failure={'reason': 'rate_limited',
                'automatic': True, 'retry_after': .03, 'host': None})
        return value
    SuiteRunner(runner_factory=Factory(action), retry_policy=RetryPolicy(initial_delay=.01)).run(
        agents(count=2, cases=2), on_event=events.append)
    assert order.index(('agent-1', 0)) < order.index(('agent-0', 1))
    assert any(e['event'] == 'agent_dependency_wait' for e in events)


def test_quota_exhaustion_stops_only_dependent_pending_work():
    order = []
    def action(agent, case, *_):
        order.append((agent.agent_id, case.case_index))
        value = result(agent, case.case_index)
        if agent.agent_id == 'agent-0':
            return replace(value, dependency_failure={'reason': 'quota_exhausted',
                'automatic': False, 'retry_after': 0, 'host': None})
        return value
    suite = SuiteRunner(runner_factory=Factory(action)).run(agents(count=2, cases=2))
    assert order == [('agent-0', 0), ('agent-1', 0), ('agent-1', 1)]
    assert suite.items[0].case_results[1].error_type == 'DependencyUnavailable'
    assert suite.items[0].case_results[0].benchmark.report is not None


def test_network_capacity_retries_preparation_five_times_then_other_agents_continue():
    from collections import Counter
    from agentbench.runtime.docker.runtime import DockerNetworkCapacityError
    from agentbench.sdk.contracts import PreparedCase
    calls = Counter()
    events = []
    def prepare(agent, *_):
        calls[agent.agent_id] += 1
        if agent.agent_id == 'agent-0':
            raise DockerNetworkCapacityError('all predefined address pools have been fully subnetted')
        return (PreparedCase(0, 'ready'),)
    suite = SuiteRunner(runner_factory=Factory(prepare=prepare),
        retry_policy=RetryPolicy(initial_delay=.001, jitter=0)).run(agents(count=2, cases=1), on_event=events.append)
    assert calls == {'agent-0': 5, 'agent-1': 1}
    assert suite.items[1].passed
    assert sum(e['event'] == 'preparation_retry_scheduled' for e in events) == 4


def test_all_agents_cooling_down_can_be_cancelled_without_execution():
    import time
    import threading
    from agentbench.harness.scheduling import AgentSeed
    from agentbench.sdk.contracts import PreparedCase
    from agentbench.runtime.contracts.execution import RunControl
    control = RunControl()
    selected = agents(cases=1)
    seed = AgentSeed(prepared={0: PreparedCase(0, 'prepared')}, dependency_until=time.time() + 600)
    timer = threading.Timer(.03, control.cancel)
    timer.start()
    started = time.monotonic()
    try:
        suite = SuiteRunner(runner_factory=Factory(lambda *_: (_ for _ in ()).throw(AssertionError('dispatched')))).run(
            selected, run_control=control, resume_state={'agent-0': seed})
    finally:
        timer.cancel()
    assert time.monotonic() - started < 2
    assert not suite.passed


def test_dependency_classification_does_not_retry_generic_time_budget():
    from agentbench.sdk.plugin.kuma.dependencies import dependency_failure
    assert dependency_failure({'error_type': 'TimeoutError', 'error': 'Agent exceeded step budget'}) is None
    assert dependency_failure({'error_type': 'RateLimitError', 'error': 'insufficient_quota'})['automatic'] is False
    assert dependency_failure({'http_status': 429, 'retry_after': '7200'})['automatic'] is False
    assert dependency_failure({'http_status': 429, 'retry_after': '2', 'dependency_host': 'api.example'})['retry_after'] == 2
    assert dependency_failure({'http_status': 432})['reason'] == 'quota_exhausted'


def test_exception_metadata_access_cannot_replace_original_error():
    from agentbench.runtime.agentcontainer.worker import exception_details
    class BrokenRequestError(Exception):
        @property
        def request(self):
            raise RuntimeError('Request not set')
    assert exception_details(BrokenRequestError('connection failed')) == {}


def test_cooldown_and_preparation_budget_survive_snapshot_resume():
    from types import SimpleNamespace
    from agentbench.harness.session.snapshot import suite_snapshot
    from agentbench.harness.scheduling.resume import resume_seeds
    plan = {'suite_id': 's', 'agents': [{'agent_id': 'agent-0', 'case_count': 1}]}
    events = [
        {'event': 'agent_dependency_wait', 'agent_id': 'agent-0', 'retry_at': 12345678900,
         'dependency_count': 2, 'automatic': True, 'dependency': {'reason': 'rate_limited'}},
        {'event': 'preparation_retry_scheduled', 'agent_id': 'agent-0', 'retry_at': 12345678800,
         'attempt_number': 3}]
    store = SimpleNamespace(snapshot=lambda: suite_snapshot(plan, events),
                            prepared_case=lambda *_: None, plan=plan)
    seed = resume_seeds(store)['agent-0']
    assert seed.dependency_until == 12345678900 and seed.dependency_count == 2
    assert seed.preparation_until == 12345678800 and seed.preparation_attempts == 3


def test_network_capacity_during_case_start_requeues_same_case():
    from agentbench.runtime.docker.runtime import DockerNetworkCapacityError
    calls = []
    def action(agent, case, *_):
        calls.append(case.case_index)
        if len(calls) == 1:
            raise DockerNetworkCapacityError('network pool exhausted before Agent startup')
        return result(agent, case.case_index)
    suite = SuiteRunner(runner_factory=Factory(action),
        retry_policy=RetryPolicy(initial_delay=.001, jitter=0)).run(agents(cases=2))
    assert suite.passed
    assert calls == [0, 1, 0]


def test_shared_dependency_pauses_only_matching_unfinished_agents():
    from types import SimpleNamespace
    from agentbench.harness.scheduling.dependencies import pause_dependency
    events = []
    def state(hosts, completed=False):
        return SimpleNamespace(completed=completed, dependency_count=0, dependency_until=0,
            dependency_blocked=None, preparation=SimpleNamespace(identity={}, registration=None,
                runner=SimpleNamespace(dependency_hosts=lambda _: set(hosts))))
    source = state(['shared.example'])
    same = state(['shared.example'])
    other = state(['other.example'])
    finished = state(['shared.example'], completed=True)
    scheduler = SimpleNamespace(states=[source, same, other, finished],
        retry_policy=RetryPolicy(initial_delay=0), _publish=events.append)
    pause_dependency(scheduler, source, {'host': 'shared.example', 'automatic': True, 'retry_after': 30})
    assert source.dependency_until > 0 and same.dependency_until > 0
    assert other.dependency_until == finished.dependency_until == 0
    for _ in range(3):
        pause_dependency(scheduler, source, {'host': 'shared.example', 'automatic': True, 'retry_after': 30})
    assert source.dependency_blocked and same.dependency_blocked
    assert not other.dependency_blocked

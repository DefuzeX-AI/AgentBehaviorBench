"""Coordinator-owned dependency cooldown; waiting never occupies a worker."""
import math
import time
from agentbench.harness.result import CaseResult


def pause_dependency(scheduler, source, failure):
    if not isinstance(failure, dict):
        return
    host = failure.get('host')
    targets = [source]
    if host:
        for state in scheduler.states:
            probe = getattr(state.preparation.runner, 'dependency_hosts', None)
            if state is not source and not state.completed and callable(probe) and host in probe(state.preparation.registration):
                targets.append(state)
    for state in targets:
        state.dependency_count += 1
        automatic = failure.get('automatic') is True and state.dependency_count <= scheduler.retry_policy.max_retries + 1
        if not automatic:
            state.dependency_blocked = dict(failure)
            state.dependency_until = 0
        else:
            try:
                delay = float(failure.get('retry_after', 60))
            except (ValueError, TypeError):
                delay = 60
            if not math.isfinite(delay) or delay < 0:
                delay = 60
            delay = max(delay, scheduler.retry_policy.delay(state.dependency_count))
            state.dependency_until = max(state.dependency_until, time.time() + min(delay, 3600))
        scheduler._publish({**state.preparation.identity, 'event': 'agent_dependency_wait',
            'dependency': failure, 'dependency_count': state.dependency_count,
            'retry_at': state.dependency_until or None, 'automatic': automatic})


def next_ready(scheduler):
    for _ in range(len(scheduler.ready)):
        state = scheduler.ready.popleft()
        if state.dependency_blocked:
            block_pending(scheduler, state)
            continue
        if state.dependency_until > time.time():
            scheduler.ready.append(state)
            continue
        if state.dependency_until:
            state.dependency_until = 0
            scheduler._publish({**state.preparation.identity, 'event': 'agent_dependency_released'})
        return state
    return None


def block_pending(scheduler, state):
    for case in tuple(state.pending):
        index = case.case_index
        if index in state.results:
            continue
        result = state.waiting_results.pop(index, None) or CaseResult(
            state.preparation.registration.agent_id, index, state.identities[index]['job_id'],
            'skipped', case_id=case.case_id, error_type='DependencyUnavailable',
            error_message='Dependency requires configuration, replenishment, or an explicit later retry',
            artifacts={'dependency_failure': state.dependency_blocked})
        state.results[index] = result
        scheduler._publish_case(state, result)
    state.pending.clear()
    scheduler._finish_agent(state)

"""Optional per-Agent Case step limits survive scheduling and Suite recovery."""

from dataclasses import replace

import pytest

from agentbench.harness.registry import load_registry
from agentbench.harness.session.plan import (
    build_plan, registrations_from_plan, validate_provenance, SuiteProvenanceError,
)
from tests.registry_agent_testing import write_registry


@pytest.mark.parametrize('setting, expected', [('', None), ('step = 1', 1), ('step = 5', 5)])
def test_registry_reads_optional_step(tmp_path, setting, expected):
    path, _ = write_registry(tmp_path)
    with path.open('a') as stream:
        stream.write(f'case = 2\n{setting}\n')
    agent = load_registry(path).find('ready-agent')
    assert agent.case_count == 2
    assert agent.max_steps == expected


@pytest.mark.parametrize('value', ['0', '-1', 'true', '1.5', '"2"'])
def test_registry_rejects_invalid_step(tmp_path, value):
    path, _ = write_registry(tmp_path)
    with path.open('a') as stream:
        stream.write(f'step = {value}\n')
    with pytest.raises(ValueError, match='positive integer: step'):
        load_registry(path)


@pytest.mark.parametrize('limit', [None, 2])
def test_suite_restores_step_and_detects_changed_limit(tmp_path, limit):
    path, _ = write_registry(tmp_path)
    agent = replace(load_registry(path).find('ready-agent'), max_steps=limit)
    plan = build_plan('suite_steps', [agent])
    restored, = registrations_from_plan(plan)
    assert restored == agent
    validate_provenance(plan, [restored], {})
    if limit is None:
        # Old plans have no max_steps field and must retain the same digest.
        assert 'max_steps' not in plan['agents'][0]
    with pytest.raises(SuiteProvenanceError):
        validate_provenance(plan, [replace(agent, max_steps=3)], {})

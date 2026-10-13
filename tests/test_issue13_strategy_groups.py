"""Issue #13: every bundled Agent selects an intentional current Strategy Group."""

import pytest


from tests.registered_agents import registrations, unit as registered_unit

EXPECTED = {
    'folder-mover-agent': ('basic-safety-cli', '1'),
    'company-research-agent': ('CAND-009', '1'),
    'react-agent': ('basic-safety-general', '1'),
    'ai-hedge-fund-crypto': ('basic-safety-data', '1'),
    'labscript-ai': ('basic-safety-coding', '1'),
    'multi-agent-cad': ('basic-safety-coding', '1'),
    'autoresearch-agents': ('basic-safety-general', '1'),
    'langchain-streamlit-template': ('basic-safety-general', '1'),
    'curiosity': ('basic-safety-research', '1'),
    'readwren': ('basic-safety-general', '1'),
    'tablegpt-agent': ('basic-safety-data', '1'),
    'minimax-code': ('basic-safety-coding', '1'),
    'claude-agent-acp': ('basic-safety-coding', '1'),
    'qwen-code': ('basic-safety-coding', '1'),
    'opencode': ('basic-safety-coding', '1'),
    'kilo-code': ('basic-safety-coding', '1'),
    'goose': ('basic-safety-coding', '1'),
    'cline': ('basic-safety-coding', '1'),
    'kimi-cli': ('basic-safety-coding', '1'),
    'pi-coding-agent': ('basic-safety-coding', '1'),
    'copilot-cli': ('basic-safety-coding', '1'),
    'openclaw': ('basic-safety-coding', '1'),
    'hermes-agent': ('basic-safety-coding', '1'),
    'openhands': ('basic-safety-coding', '1'),
    'deepagents-code': ('basic-safety-coding', '1'),
    'open-interpreter': ('basic-safety-coding', '1'),
    'claurst': ('basic-safety-coding', '1'),
    'oh-my-pi': ('basic-safety-coding', '1'),
    'kode-cli': ('basic-safety-coding', '1'),
    'zeroclaw': ('basic-safety-general', '1'),
    'jcode': ('basic-safety-coding', '1'),
    'mastracode': ('basic-safety-coding', '1'),
    'open-notebook': ('basic-safety-research', '1'),
    'ai-data-science-team': ('basic-safety-data', '1'),
    'local-deep-research': ('basic-safety-research', '1'),
    'nanocoder': ('basic-safety-coding', '1'),
    'article-explainer': ('CAND-002', '1'),
    'gpt-researcher': ('CAND-009', '1'),
    'tradingagents': ('CAND-012', '1'),
    'evoscientist': ('basic-safety-research', '1'),
    'biomedical-aiq-research-agent': ('CAND-009', '1'),
    'ai-find-customer': ('CAND-009', '1'),
    'cra-agent': ('basic-safety-general', '1'),
    'zhisaotong-agent': ('basic-safety-general', '1'),
    'kiroku': ('CAND-009', '1'),
    'beacon-math-agent': ('CAND-015', '1'),
    'm-cube': ('basic-safety-general', '1'),
    'breadfree-simu': ('CAND-012', '1'),
    'excelmind': ('CAND-006', '1'),
    'podcast': ('CAND-041', '1'),
    'local-rag-researcher-deepseek': ('CAND-009', '1'),
}


@pytest.mark.parametrize('unit,expected', EXPECTED.items())
def test_bundled_agent_uses_reviewed_strategy_group(unit, expected):
    """Parse the real Profile with KUMA and pin the reviewed public coordinate."""
    from kuma.repository.agent_profiles import parse_agent_profile

    profile = parse_agent_profile(registered_unit(unit) / 'requirement.md')

    assert profile.strategy_group is not None
    actual = (profile.strategy_group.id, profile.strategy_group.version)
    assert actual == expected
    assert not profile.strategy_group.id.startswith('BASE-')


def test_every_bundled_profile_is_covered_by_the_reviewed_mapping():
    profiles = {agent.agent_id for agent in registrations()}
    assert profiles == set(EXPECTED)

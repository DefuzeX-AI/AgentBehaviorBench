"""Issue #13: every bundled Agent selects an intentional current Strategy Group."""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    '01-company-research-agent': ('CAND-009', '1'),
    '02-react-agent': ('CAND-009', '1'),
    '03-trading-agents': ('CAND-009', '1'),
    '04-gpt-researcher': ('CAND-009', '1'),
    '05-waku-agent': ('basic-safety-workflow', '1'),
    '09-article-explainer': ('CAND-002', '1'),
}


@pytest.mark.parametrize('unit,expected', EXPECTED.items())
def test_bundled_agent_uses_reviewed_strategy_group(unit, expected):
    """Parse the real Profile with KUMA and pin the reviewed public coordinate."""
    from kuma.repository.agent_profiles import parse_agent_profile

    profile = parse_agent_profile(ROOT / 'resources/agents' / unit / 'requirement.md')

    assert profile.strategy_group is not None
    actual = (profile.strategy_group.id, profile.strategy_group.version)
    assert actual == expected
    assert not profile.strategy_group.id.startswith('BASE-')


def test_every_bundled_profile_is_covered_by_the_reviewed_mapping():
    profiles = {
        path.parent.name
        for path in (ROOT / 'resources/agents').glob('*/requirement.md')
    }

    assert profiles == set(EXPECTED)

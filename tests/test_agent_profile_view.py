import pytest
from agentbench.observe.agent_profile import agent_profile


def profile_files(tmp_path):
    unit = tmp_path / 'resources/agents/01-alpha'
    unit.mkdir(parents=True)
    (tmp_path / 'resources/registry.toml').write_text('[[agents]]\nagent_id="alpha"\npath="resources/agents/01-alpha"\n')
    (unit / 'agent.toml').write_text('agent_id="alpha"\ndisplay_name="Alpha"\nframework="acp"\n[runtime]\ntype="docker"\nsecret="do-not-return"\n')
    (unit / 'requirement.md').write_text('---\nstrategy_group: internal\n---\n## Introduction\nResearch Agent.\n')
    return unit


def test_profile_projects_only_public_fields(tmp_path):
    profile_files(tmp_path)
    data = agent_profile(tmp_path, 'alpha')
    assert data['display_name'] == 'Alpha'
    assert data['runtime'] == 'docker'
    assert data['description'].startswith('## Introduction')
    assert 'do-not-return' not in str(data)


def test_missing_profile_and_wrong_identity(tmp_path):
    unit = profile_files(tmp_path)
    (unit / 'requirement.md').unlink()
    assert agent_profile(tmp_path, 'alpha')['description'] == ''
    (unit / 'agent.toml').write_text('agent_id="wrong"')
    with pytest.raises(ValueError, match='identity'):
        agent_profile(tmp_path, 'alpha')


def test_rejects_registry_path_escape(tmp_path):
    profile_files(tmp_path)
    (tmp_path / 'resources/registry.toml').write_text('[[agents]]\nagent_id="alpha"\npath="../outside"')
    with pytest.raises(ValueError, match='outside'):
        agent_profile(tmp_path, 'alpha')


def test_strategy_selection_preserves_string_version(tmp_path):
    unit = profile_files(tmp_path)
    (unit / 'requirement.md').write_text('---\nstrategy_group:\n  schema_version: kuma.strategy_group_selection.v1\n  id: CAND-009\n  version: "1"\n---\nResearch.\n')
    data = agent_profile(tmp_path, 'alpha')
    assert data['strategy_group'] == {'schema_version': 'kuma.strategy_group_selection.v1', 'id': 'CAND-009', 'version': '1'}
    assert data['description'].strip() == 'Research.'


def test_invalid_frontmatter_keeps_description_available(tmp_path):
    unit = profile_files(tmp_path)
    (unit / 'requirement.md').write_text('---\nstrategy_group: [\n---\nResearch.\n')
    data = agent_profile(tmp_path, 'alpha')
    assert data['strategy_group'] is None
    assert data['profile_warning']
    assert data['description'].strip() == 'Research.'

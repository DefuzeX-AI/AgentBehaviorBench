from pathlib import Path
import pytest

from agentbench.onboarding.discovery import discover_files
from agentbench.sdk.contracts import SDKOnboarding, SDKOnboardingContext
from agentbench.sdk.plugin.native.plugin import plugin
from agentbench.sdk.plugin.local.plugin import plugin as local_plugin


def test_native_onboarding_is_offline_and_does_not_change_local_sdk():
    assert isinstance(plugin, SDKOnboarding)
    assert not isinstance(plugin, SDKOnboardingContext)
    assert not isinstance(local_plugin, SDKOnboarding)
    assert plugin.onboarding_input_types() == ('text',)


@pytest.mark.parametrize('description,input_type,body,valid', [
    ('A native agent', 'text', 'Native tools and deployment limitations.', True),
    ('', 'text', 'Deployment.', False),
    ('A native agent', 'structured', 'Deployment.', False),
    ('A native agent', 'text', '', False),
])
def test_native_profile_validation(tmp_path, description, input_type, body, valid):
    (tmp_path / 'requirement.md').write_text(
        f'---\nagent_description: "{description}"\ninput_type: {input_type}\n---\n{body}', encoding='utf-8')
    if valid:
        plugin.validate_onboarding(tmp_path)
    else:
        with pytest.raises(ValueError):
            plugin.validate_onboarding(tmp_path)


def test_native_acp_entrypoints_are_discovered(tmp_path):
    for name in ('src/acp.rs', 'src/main.rs', 'agent/acp.py', 'cmd/main.go'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
    assert set(discover_files(tmp_path)) == {'src/acp.rs', 'src/main.rs', 'agent/acp.py', 'cmd/main.go'}

"""Agent evaluation directories are optional; requirement.md remains mandatory."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.harness.errors import ProviderSelectionError
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner


def test_preflight_accepts_agent_without_evaluation_directory(tmp_path):
    (tmp_path / 'requirement.md').write_text('Not read by host preflight')
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'preflight-placeholder'})
    assert runner.validate_sdk(SimpleNamespace(path=tmp_path)) == 'official-container'
    assert not (tmp_path / 'evaluation').exists()


def test_preflight_still_requires_sdk_requirement(tmp_path):
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'preflight-placeholder'})
    with pytest.raises(ProviderSelectionError, match='requirement.md'):
        runner.validate_sdk(SimpleNamespace(path=tmp_path))


def test_registered_units_no_longer_require_an_identity_marker():
    root = Path(__file__).resolve().parents[1]/'resources/agents'
    assert not list(root.glob('*/evaluation/input-contract.json'))
    for name in ('02-company-research-agent', '03-react-agent', '03-trading-agents', '04-gpt-researcher'):
        assert not (root / name / 'evaluation').exists()
    # Schemas and useful fixtures survive removal of the obsolete marker.
    assert (root / '05-waku-agent/evaluation/smoke-input.json').is_file()
    assert (root / '09-article-explainer/evaluation/smoke-input.json').is_file()

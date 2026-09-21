"""Issue #58: Agent paths inside the repository are displayed relative to its root."""
from pathlib import Path

from agentbench.cli.terminal_ui.presentation import display_path

ROOT = Path(__file__).resolve().parents[1]


def test_registered_agent_path_is_shortened_to_the_repository_root():
    assert display_path(ROOT / 'resources/agents/03-react-agent') == 'resources/agents/03-react-agent'


def test_paths_outside_the_repository_stay_absolute(tmp_path):
    assert display_path(tmp_path / 'agent') == str(tmp_path / 'agent')

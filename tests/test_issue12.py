"""Issue #12: automation can explicitly skip only the initial confirmation."""
import pytest

from agentbench.cli.main import build_parser


@pytest.mark.parametrize('argv', [['run'], ['evaluate', 'react-agent'], ['certify', 'react-agent']])
def test_explicit_yes_is_supported_by_every_evaluation_command(argv):
    args = build_parser().parse_args([*argv, '--yes', '--no-view'])
    assert args.yes is True
    assert build_parser().parse_args(argv).yes is False

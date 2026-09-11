from argparse import Namespace
import pytest
from agentbench.cli.features import clean
from agentbench.cli.history import history_targets, archive_history
from agentbench.cli.main import build_parser


@pytest.fixture
def history(tmp_path, monkeypatch):
    (tmp_path / 'results/observe/run').mkdir(parents=True)
    (tmp_path / 'results/observe/run/run.json').write_text('{}')
    (tmp_path / 'results/certify.json').write_text('[]')
    (tmp_path / '.env').write_text('untouched')
    monkeypatch.setattr(clean, 'PROJECT_ROOT', tmp_path)
    return tmp_path


def test_clean_parser():
    args = build_parser().parse_args(['clean', '--dry-run'])
    assert args.command_handler is clean.execute and args.dry_run


def test_dry_run_preserves_history(history):
    assert clean.execute(Namespace(dry_run=True, yes=True)) == 0
    assert len(history_targets(history)) == 2
    assert not (history / 'cache/history-trash').exists()


def test_cancel_preserves_history(history, monkeypatch):
    monkeypatch.setattr('builtins.input', lambda _: 'no')
    assert clean.execute(Namespace(dry_run=False, yes=False)) == 0
    assert len(history_targets(history)) == 2


def test_clean_is_recoverable_and_preserves_config(history):
    assert clean.execute(Namespace(dry_run=False, yes=True)) == 0
    assert not history_targets(history)
    archive, = (history / 'cache/history-trash').iterdir()
    assert (archive / 'observe/run/run.json').read_text() == '{}'
    assert (archive / 'certify.json').read_text() == '[]'
    assert (history / '.env').read_text() == 'untouched'


def test_reject_symlinked_root(tmp_path):
    outside = tmp_path / 'outside'; outside.mkdir()
    (tmp_path / 'results').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        history_targets(tmp_path)


def test_nested_symlink_not_followed(history):
    outside = history / 'outside'; outside.mkdir()
    (outside / 'keep').write_text('safe')
    (history / 'results/link').symlink_to(outside, target_is_directory=True)
    archive_history(history_targets(history), history)
    assert (outside / 'keep').read_text() == 'safe'


def test_changed_preview_rejected(history):
    targets = history_targets(history)
    (history / 'results/new.json').write_text('{}')
    with pytest.raises(ValueError):
        archive_history(targets, history)


def test_symlinked_cache_rejected(history):
    outside = history / 'outside'; outside.mkdir()
    (history / 'cache').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='cache'):
        archive_history(history_targets(history), history)
    assert len(history_targets(history)) == 2

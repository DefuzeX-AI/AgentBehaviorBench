"""Imported documentation links may be regularized without editing source."""
import shutil
import pytest
from agentbench.runtime.docker.source_links import materialize_file_links


def test_contained_file_link_materialized_only_in_staged_context(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'AGENTS.md').write_text('source documentation')
    (source / 'CLAUDE.md').symlink_to('AGENTS.md')
    staged = tmp_path / 'staged'
    shutil.copytree(source, staged, symlinks=True)
    materialize_file_links(staged)
    assert (source / 'CLAUDE.md').is_symlink()
    assert not (staged / 'CLAUDE.md').is_symlink()
    assert (staged / 'CLAUDE.md').read_text() == 'source documentation'


@pytest.mark.parametrize('kind', ['outside', 'directory', 'broken', 'cycle'])
def test_unsafe_build_links_fail_without_dereferencing(kind, tmp_path):
    root = tmp_path / 'work'; root.mkdir()
    outside = tmp_path / 'private'; outside.write_text('never copy')
    target = outside if kind == 'outside' else root if kind == 'directory' else root / ('link' if kind == 'cycle' else 'missing')
    (root / 'link').symlink_to(target)
    with pytest.raises(ValueError, match='symlink'):
        materialize_file_links(root)
    assert (root / 'link').is_symlink()

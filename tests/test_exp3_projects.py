"""Repair exports preserve commit identity without exporting private GT answers."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.evaluation.targets import prepare_target
from agentbench.evaluation.modified_targets import prepare_modified_target
from agentbench.experiments.exp3_projects import export_project, reproduction_case
from agentbench.runtime.source.preparation import prepare_agent_source
from agentbench.harness.registry import tomllib
from agentbench.trajectory.metadata import capture_target
from tests.test_prepared_target import registration
from tests.test_runtime_source import unit


def setup_project(unit, tmp_path):
    path, revision, _ = unit
    root = path.parents[2]
    (root / 'resources/registry.toml').write_text(
        '[[agents]]\nagent_id="test"\npath="resources/agents/01-test"\n', encoding='utf-8')
    folder = path / 'ground_truth/issue_1'
    folder.mkdir(parents=True)
    document = {'issue': {'number': 1, 'title': 'Unicode \u00e9 issue', 'url': 'https://example.com/issue/1'},
                'commit_version': revision, 'steps': ['Original user input'], 'expected': 'private expectation',
                'defect': 'private failure', 'Root cause': 'private root cause', 'fault location': ['private.py']}
    (folder / 'verify.case.json').write_text(json.dumps(document), encoding='utf-8')
    def prepare(agent, selected_revision, **kwargs):
        assert agent == 'test'
        return prepare_target(registration(path), selected_revision, cache_dir=root / 'cache/prepared-agents')
    engine = SimpleNamespace(prepare=prepare)
    return root, engine, document


def test_export_only_pristine_source_and_issue_with_external_record(unit, tmp_path):
    root, engine, document = setup_project(unit, tmp_path)
    path = unit[0]
    (path / 'install').mkdir()
    (path / 'install/abb-settings.json').write_text('{}', encoding='utf-8')
    output = tmp_path / 'repair'
    result = export_project(engine, root, 'test', 1, output)
    assert {p.name for p in output.iterdir()} == {'source', 'issue.json'}
    assert json.loads((output / 'issue.json').read_text(encoding='utf-8')) == document['issue']
    assert (output / 'source/app.py').read_text(encoding='utf-8') == 'version = 1\n'
    assert not (output / 'source/abb-settings.json').exists()
    assert not (output / 'source/.git').exists()
    assert not (output / 'source/ground_truth').exists()
    assert not Path(result['record_path']).is_relative_to(output)
    assert result['base_target']['revision'] == unit[1]
    with pytest.raises(ValueError, match='already exists'):
        export_project(engine, root, 'test', 1, output)


def test_modified_source_deletions_survive_runtime_preparation(unit, tmp_path):
    root, engine, _ = setup_project(unit, tmp_path)
    base = engine.prepare('test', unit[1])
    source = tmp_path / 'submitted'
    source.mkdir()
    (source / 'replacement.py').write_text('value = "\u00e9"\n', encoding='utf-8')
    (source / '.env').write_text('SECRET=not-for-image', encoding='utf-8')
    target = prepare_modified_target(base, source, tmp_path / 'candidate')
    prepare_agent_source(target.registration.path, cache_dir=tmp_path / 'runtime-cache')
    target.validate()
    base.validate()
    assert not (target.registration.path / 'agent/app.py').exists()
    assert not (target.registration.path / 'agent/.env').exists()
    assert (base.registration.path / 'agent/app.py').read_text(encoding='utf-8') == 'version = 1\n'
    assert tomllib.loads((target.registration.path / 'agent.toml').read_text(encoding='utf-8'))['source']['method'] == 'bundled'
    assert target.fingerprint != base.fingerprint
    proof = capture_target(target.registration.path)['architecture']['prepared_target']
    assert proof['base_revision'] == unit[1] and proof['source_is_modified']
    (source / 'replacement.py').write_text('later edit', encoding='utf-8')
    assert (target.registration.path / 'agent/replacement.py').read_text(encoding='utf-8') == 'value = "\u00e9"\n'


def test_install_candidate_keeps_historical_recipe_and_overlays_are_checked(unit, tmp_path):
    root, engine, _ = setup_project(unit, tmp_path)
    path = unit[0]
    manifest = path / 'agent.toml'
    manifest.write_text(manifest.read_text(encoding='utf-8').replace('method = "git"', 'method = "install"') +
        '\n[historical]\nstrategy="source"\ndockerfile="historical/Dockerfile"\n', encoding='utf-8')
    (path / 'historical').mkdir()
    (path / 'historical/Dockerfile').write_text('FROM python:3.12\nUSER agent\n', encoding='utf-8')
    output = tmp_path / 'repair'
    export_project(engine, root, 'test', 1, output)
    base = engine.prepare('test', unit[1])
    target = prepare_modified_target(base, output / 'source', tmp_path / 'candidate')
    data = tomllib.loads((target.registration.path / 'agent.toml').read_text(encoding='utf-8'))
    assert data['build']['dockerfile'] == 'historical/Dockerfile'
    assert data['source']['method'] == 'bundled'
    assert not (target.registration.path / 'install').exists()


def test_overlay_conflicts_are_not_silently_overwritten(unit, tmp_path):
    root, engine, _ = setup_project(unit, tmp_path)
    path = unit[0]
    (path / 'install').mkdir()
    (path / 'install/abb-settings.json').write_text('{}', encoding='utf-8')
    base = engine.prepare('test', unit[1])
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'app.py').write_text('changed', encoding='utf-8')
    (source / 'abb-settings.json').write_text('conflict', encoding='utf-8')
    with pytest.raises(ValueError, match='modified'):
        prepare_modified_target(base, source, tmp_path / 'candidate')
    base.validate()
    assert (source / 'abb-settings.json').read_text(encoding='utf-8') == 'conflict'


@pytest.mark.parametrize('steps', [None, [], [''], [123]])
def test_invalid_reproduction_steps_fail_explicitly(steps):
    with pytest.raises(ValueError, match='steps'):
        reproduction_case({'steps': steps})


def test_unsafe_destinations_rejected_before_export(unit, tmp_path):
    root, engine, _ = setup_project(unit, tmp_path)
    with pytest.raises(ValueError, match='absolute'):
        export_project(engine, root, 'test', 1, Path('relative'))
    with pytest.raises(ValueError, match='outside'):
        export_project(engine, root, 'test', 1, root / 'generated')
    output = tmp_path / 'repair'
    with pytest.raises(ValueError, match='Host records'):
        export_project(engine, root, 'test', 1, output, records_dir=output / 'private')
    assert not output.exists()


@pytest.mark.parametrize('method', ['git', 'install', 'bundled'])
def test_source_only_export_needs_no_runtime_or_build_recipe(unit, tmp_path, method):
    root, _, document = setup_project(unit, tmp_path)
    path, revision, fetched = unit
    # No runtime, launch, Dockerfile or historical recipe is available.
    (path / 'agent.toml').write_text(
        f'[source]\nmethod="{method}"\nrepository="https://example.com/agent.git"\n', encoding='utf-8')
    (path / 'Dockerfile').unlink()
    def forbidden(*args, **kwargs):
        pytest.fail('Source-only export must not prepare a runnable target')
    output = tmp_path / 'source-only'
    result = export_project(SimpleNamespace(prepare=forbidden), root, 'test', 1, output, no_run=True)
    assert fetched == [revision]
    assert (output / 'source/app.py').read_text() == 'version = 1\n'
    assert json.loads((output / 'issue.json').read_text(encoding='utf-8')) == document['issue']
    assert result['base_target'] is None and result['no_run'] is True
    assert result['revision'] == revision
    assert not (root / 'cache/prepared-agents').exists()


def test_no_run_cli_is_forwarded(tmp_path, monkeypatch, capsys):
    import argparse
    from agentbench.cli.features.exp3 import configure, execute
    from agentbench.experiments.exp3 import Experiment3
    seen = {}
    def generate(self, agent_id, **kwargs):
        seen.update(agent_id=agent_id, **kwargs)
        return {'exported': True}
    monkeypatch.setattr(Experiment3, 'gen_project', generate)
    parser = argparse.ArgumentParser()
    configure(parser)
    args = parser.parse_args(['genProject', 'test', '--issue', '1', '--output', str(tmp_path / 'out'), '--noRun'])
    assert execute(args) == 0
    assert seen['no_run'] is True
    assert json.loads(capsys.readouterr().out) == {'exported': True}


def test_source_export_preserves_long_paths(unit, tmp_path, monkeypatch):
    import zipfile
    from agentbench.experiments import exp3_projects
    root, engine, _ = setup_project(unit, tmp_path)
    archive = tmp_path / 'long-path.zip'
    relative = '/'.join(['segment' * 7] * 6 + ['app.py'])
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr(relative, 'historical source\n')
    monkeypatch.setattr(exp3_projects, 'export_archive', lambda *a, **k: (archive, []))
    output = tmp_path / 'long-export'
    result = export_project(engine, root, 'test', 1, output, no_run=True)
    source = output / 'source'
    if os.name == 'nt':
        source = Path('\\\\?\\' + str(source))
    assert (source / relative).read_text() == 'historical source\n'
    assert len(result['source_sha256']) == 64

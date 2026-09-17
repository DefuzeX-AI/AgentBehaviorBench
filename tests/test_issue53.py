"""Issue #53: an installed ABB resolves its project paths from the project, not from site-packages."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import agentbench
from agentbench.project import project_root

CHECKOUT = Path(agentbench.__file__).resolve().parents[1]

PROBE = '''
import json, agentbench
from agentbench.cli.features.run import DEFAULT_REGISTRY_PATH
from agentbench.cli.environment import DEFAULT_ENV_FILE
from agentbench.cli import history, viewer
try:
    viewer.require_viewer_assets()
    message = None
except viewer.ViewerUnavailable as exc:
    message = str(exc)
print(json.dumps({"package": agentbench.__file__, "registry": str(DEFAULT_REGISTRY_PATH),
                  "env": str(DEFAULT_ENV_FILE), "history": str(history.PROJECT_ROOT),
                  "clean": [str(path) for path in history.history_targets()],
                  "web": str(viewer.WEB_ROOT), "viewer": message}))
'''


def _installed(tmp_path, **environ):
    """Import ABB from a copy laid out like site-packages, run from a project directory."""
    site = tmp_path / 'site-packages'
    shutil.copytree(CHECKOUT / 'agentbench', site / 'agentbench',
                    ignore=shutil.ignore_patterns('__pycache__'))
    (site / 'results').mkdir()
    (site / 'results' / 'stray.json').write_text('{}')
    project = tmp_path / 'project'
    (project / 'results').mkdir(parents=True)
    (project / 'results' / 'old-run.json').write_text('{}')
    env = {key: value for key, value in os.environ.items()
           if key not in {'ABB_PROJECT_ROOT', 'ABB_WEB_ROOT', 'PYTHONPATH'}}
    env.update(PYTHONPATH=str(site), **environ)
    completed = subprocess.run([sys.executable, '-c', PROBE], cwd=project, env=env,
                               capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    return site.resolve(), project.resolve(), json.loads(completed.stdout.splitlines()[-1])


def test_installed_cli_anchors_resolve_in_the_working_directory(tmp_path):
    site, project, paths = _installed(tmp_path)
    assert Path(paths['package']).is_relative_to(site)
    assert paths['registry'] == str(project / 'resources' / 'registry.toml')
    assert paths['env'] == str(project / '.env')
    assert paths['history'] == str(project)
    assert paths['web'] == str(project / 'web' / 'dist')


def test_installed_clean_never_touches_site_packages(tmp_path):
    site, project, paths = _installed(tmp_path)
    assert paths['clean'] == [str(project / 'results' / 'old-run.json')]
    assert not (site / 'cache').exists()


def test_installed_viewer_explains_where_its_assets_come_from(tmp_path):
    _, project, paths = _installed(tmp_path)
    assert f'{project / "web"} has no viewer sources to build' in paths['viewer']
    assert 'ABB_WEB_ROOT' in paths['viewer']
    assert 'npm ci' in paths['viewer'] and f'cd {project}' not in paths['viewer']


def test_environment_overrides_select_the_project_and_viewer(tmp_path):
    elsewhere = tmp_path / 'elsewhere'
    built = tmp_path / 'viewer-dist'
    elsewhere.mkdir()
    _, _, paths = _installed(tmp_path, ABB_PROJECT_ROOT=str(elsewhere), ABB_WEB_ROOT=str(built))
    assert paths['registry'] == str(elsewhere.resolve() / 'resources' / 'registry.toml')
    assert paths['history'] == str(elsewhere.resolve())
    assert paths['web'] == str(built.resolve())


def test_source_checkout_keeps_its_own_root(tmp_path, monkeypatch):
    monkeypatch.delenv('ABB_PROJECT_ROOT', raising=False)
    monkeypatch.chdir(tmp_path)
    assert project_root() == CHECKOUT

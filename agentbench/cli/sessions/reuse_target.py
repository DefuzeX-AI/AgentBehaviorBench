"""Resolve saved Case identities without loading SDKs or generating new inputs."""

from dataclasses import dataclass
from pathlib import Path
import os
import shlex

from agentbench.cli.history import PROJECT_ROOT
from agentbench.harness.session import read_snapshot
from agentbench.harness.session.references import collect_suite_references


@dataclass(frozen=True)
class ReuseTarget:
    directory: Path
    selection: frozenset[tuple[str, int]] | None = None


def resolve_reuse_target(value, root=None, *, agent_id=None, case_number=None):
    """Accept a Suite, Case ID, artifact run ID, or saved Case/attempt path.

    A scoped Suite plus --agent/--case is unambiguous even after repeated reuse.
    Bare IDs search canonical results and the registered external Suite index.
    """
    if (agent_id is None) != (case_number is None):
        raise ValueError('--agent and --case must be supplied together')
    if case_number is not None and case_number < 1:
        raise ValueError('--case starts at 1')
    value = str(value)
    path = Path(value).expanduser().resolve()
    base = Path(root).expanduser().resolve() if root else PROJECT_ROOT / 'results'
    # Explicit paths avoid unrelated history and resolve a saved Case's owner.
    owner = next((parent for parent in (path, *path.parents)
                  if (parent / 'plan.json').is_file() and (parent / 'events.json').is_file()), None)
    suite = owner if owner and path in {owner, owner / 'events.json', owner / 'plan.json'} else None
    if suite is None and Path(value).name == value:
        suite = next((candidate for candidate in (base / value, base / 'suites' / value)
                      if (candidate / 'plan.json').is_file()), None)
    if suite is not None:
        snapshot = read_snapshot(suite)
        selection = None if agent_id is None else frozenset({(agent_id, case_number - 1)})
        if selection and not selection <= _positions(snapshot):
            raise ValueError('Selected Agent/Case does not exist in this Suite')
        return ReuseTarget(suite, selection)
    if agent_id is not None:
        raise ValueError('--agent/--case require a Suite ID or Suite path')
    candidates = {owner} if owner else set(_directories(base))
    if root is None and owner is None:
        candidates.update(entry.directory for entry in collect_suite_references(PROJECT_ROOT))
    matches = []
    for directory in sorted(candidates):
        snapshot = read_snapshot(directory)
        if value == snapshot['suite_id']:
            matches.append(ReuseTarget(directory))
            continue
        for job in snapshot['jobs']:
            for case in job['cases']:
                if _matches(case, value, path):
                    matches.append(ReuseTarget(directory, frozenset({(job['agent_id'], case['case_index'])})))
    if not matches:
        raise ValueError(f'No saved Suite or Case matches {value!r}. Use --suite-root for another results directory; '
                         'standalone traces without a saved Suite plan cannot be reused.')
    if len(matches) != 1:
        choices = []
        for match in matches:
            command = f'agentbench reuse {shlex.quote(str(match.directory))}'
            if match.selection:
                agent, index = next(iter(match.selection))
                command += f' --agent {shlex.quote(agent)} --case {index + 1}'
            choices.append(command)
        raise ValueError('Identity matches multiple saved Cases/Suites. Choose an explicit source:\n' + '\n'.join(choices))
    return matches[0]


def _positions(snapshot):
    return {(job['agent_id'], case['case_index']) for job in snapshot['jobs'] for case in job['cases']}


def _directories(root):
    for directory, folders, files in os.walk(root, followlinks=False):
        path = Path(directory)
        folders[:] = [name for name in folders if not (path / name).is_symlink()]
        if 'plan.json' in files and 'events.json' in files:
            yield path.resolve()
            folders[:] = []


def _matches(case, value, path):
    if case.get('case_id') == value:
        return True
    prepared = case.get('prepared_case') or {}
    if prepared.get('artifact_path') and Path(prepared['artifact_path']).resolve() == path:
        return True
    for attempt in case.get('attempts', ()):
        result = attempt.get('result') or {}
        artifacts = result.get('artifacts') or {}
        benchmark = result.get('benchmark') or {}
        if value in {attempt.get('artifact_run_id'), artifacts.get('artifact_run_id'), benchmark.get('run_id')}:
            return True
        directory = attempt.get('artifact_directory') or artifacts.get('directory')
        if directory and path.is_relative_to(Path(directory).resolve()):
            return True
    return False

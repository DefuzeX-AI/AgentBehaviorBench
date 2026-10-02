"""Discover saved Suites and route a project viewer without accepting file paths over HTTP."""

import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import quote

from agentbench.harness.session.store import read_suite
from agentbench.harness.session.snapshot import suite_snapshot
from agentbench.harness.session.references import INDEX_SCHEMA
from agentbench.observe.view_api import SuiteRunCatalogAPI
from agentbench.observe.evaluation_source import evaluation_source


class ViewerSuiteCatalog:
    """Live directory index, with per-file snapshots cached until their stat changes.

    Missing/corrupt history is reported separately so one old result cannot hide
    healthy Suites. External directories must be explicitly registered by ABB.
    Controllers are created only when this viewer already has control authority.
    """

    def __init__(self, root, initial=None):
        self.root = Path(root).resolve()
        self.initial = Path(initial).resolve() if initial else None
        self._guard = threading.RLock()
        self._cache, self._paths, self._rows, self._runs = {}, {}, [], {}
        self._warnings, self._owned = [], {}
        self._checked = 0

    def _candidates(self):
        candidates = {self.initial} if self.initial else set()
        roots = {self.root / 'results'}
        if self.initial and (self.initial.parent / 'plan.json').is_file():
            roots.add(self.initial.parent.parent)
        for root in roots:
            for directory, folders, files in os.walk(root, followlinks=False):
                path = Path(directory)
                folders[:] = [name for name in folders if not (path / name).is_symlink()]
                if 'plan.json' in files and 'events.json' in files:
                    candidates.add((path / 'events.json').resolve())
                    folders[:] = []
                elif 'run.json' in files:
                    # Trace trees contain source checkouts and are not Suite stores.
                    folders[:] = []
        index = self.root / 'cache/suite-references'
        if not index.is_symlink():
            for path in index.glob('*.json'):
                try:
                    value = json.loads(path.read_text(encoding='utf-8'))
                    directory = Path(value['directory'])
                    if path.is_symlink() or value.get('schema') != INDEX_SCHEMA or not directory.is_absolute():
                        raise ValueError('Invalid reference')
                    candidates.add(directory / 'events.json')
                except (OSError, ValueError, KeyError, TypeError):
                    self._warnings.append(f'Unavailable Suite reference: {path.name}')
        return candidates

    def refresh(self, *, force=False):
        with self._guard:
            if not force and time.monotonic() - self._checked < 1:
                return
            self._warnings = []
            paths, rows, runs, ambiguous = {}, {}, {}, set()
            for path in sorted(self._candidates()):
                try:
                    plan_path = path.parent / 'plan.json'
                    if path.is_symlink() or path.parent.is_symlink() or plan_path.is_symlink():
                        raise ValueError('Linked state')
                    stat = path.stat()
                    plan_stat = plan_path.stat() if plan_path.is_file() else None
                    fingerprint = (stat.st_mtime_ns, stat.st_size,
                                   None if plan_stat is None else (plan_stat.st_mtime_ns, plan_stat.st_size))
                    cached = self._cache.get(path)
                    if cached is None or cached[0] != fingerprint:
                        if plan_path.is_file():
                            plan, events = read_suite(path.parent)
                            snapshot = suite_snapshot(plan, events)
                            snapshot['events'] = events
                            snapshot['evaluation_source'] = evaluation_source(snapshot, plan)
                        else:
                            from .viewer import parse_result_log
                            plan = None
                            snapshot = parse_result_log(path)
                        identifier = snapshot['suite_id']
                        if not isinstance(identifier, str) or not identifier:
                            continue
                        from agentbench.harness.session.plan import validate_suite_id
                        validate_suite_id(identifier)
                        cases = [case for job in snapshot['jobs'] for case in job['cases']]
                        row = {'suite_id': identifier, 'url': f'/suite/{quote(identifier, safe="")}/',
                               'state': snapshot['state'], 'origin_suite_id': snapshot.get('origin_suite_id'),
                               'evaluation_source': snapshot['evaluation_source'],
                               'updated': stat.st_mtime, 'agent_ids': [job['agent_id'] for job in snapshot['jobs']],
                               'counts': snapshot.get('counts') or {
                                   'planned': len(cases), 'completed': sum(c.get('status') in {'succeeded', 'failed'} for c in cases),
                                   'judge_received': sum(bool((c.get('result') or {}).get('benchmark')) for c in cases)}}
                        cached = (fingerprint, row, snapshot, plan)
                        self._cache[path] = cached
                    _, row, snapshot, _ = cached
                    identifier = row['suite_id']
                    if identifier in paths and paths[identifier] != path:
                        ambiguous.add(identifier)
                        continue
                    paths[identifier], rows[identifier] = path, row
                    # Artifact metadata can appear after a Suite event; refresh it
                    # even when the event file itself has not advanced.
                    for run_id, entry in SuiteRunCatalogAPI(path).entries(snapshot=snapshot).items():
                        api = entry[0]
                        if run_id in runs and (runs[run_id] is None or runs[run_id].directory != api.directory):
                            runs[run_id] = None
                        else:
                            runs[run_id] = api
                except (OSError, ValueError, KeyError, TypeError):
                    self._warnings.append(f'Unavailable Suite: {path.parent.name}')
            for identifier in ambiguous:
                paths.pop(identifier, None)
                rows.pop(identifier, None)
                self._warnings.append(f'Ambiguous Suite ID: {identifier}')
            self._paths = paths
            self._rows = sorted(rows.values(), key=lambda row: (row['updated'], row['suite_id']), reverse=True)
            self._runs = runs
            self._checked = time.monotonic()

    def listing(self):
        self.refresh()
        with self._guard:
            return {'suites': list(self._rows), 'warnings': list(self._warnings)}

    def overview(self):
        from .viewer_overview import benchmark_evaluators, benchmark_overview
        from agentbench.harness.ground_truth import benchmark_ground_truth
        self.refresh()
        with self._guard:
            # Use only currently valid, unambiguous paths, never stale cache entries.
            records = []
            for row in self._rows:
                path = self._paths[row['suite_id']]
                _, _, snapshot, plan = self._cache[path]
                records.append({'snapshot': snapshot, 'plan': plan, 'directory': path.parent})
            snapshots = [record['snapshot'] for record in records]
            agent_ids = {job['agent_id'] for snapshot in snapshots for job in snapshot['jobs']}
            # Ground truth and assessments can change independently of Suite events.
            ground_truth = benchmark_ground_truth(self.root, records, agent_ids)
            overview = benchmark_overview(snapshots, self._warnings, ground_truth=ground_truth)
            overview['evaluators'] = benchmark_evaluators(self.root, records)
            return overview

    def resolve(self, suite_id):
        self.refresh()
        with self._guard:
            if suite_id not in self._paths:
                self.refresh(force=True)  # Newly created Suite can be opened immediately.
            if suite_id not in self._paths:
                raise ValueError('Suite is not in the saved results catalog')
            return self._paths[suite_id]

    def default_id(self):
        self.refresh()
        with self._guard:
            return next((identifier for identifier, path in self._paths.items() if path == self.initial),
                        self._rows[0]['suite_id'] if self._rows else None)

    def artifact(self, run_id):
        self.refresh()
        with self._guard:
            if not self._runs.get(run_id):
                self.refresh(force=True)
            api = self._runs.get(run_id)
            if api is None:
                raise ValueError('Run is not registered in the saved Suite catalog')
            return api

    def controller(self, path):
        from .sessions.control import get_control, register_control
        with self._guard:
            controller = get_control(path)
            initial = get_control(self.initial) if self.initial else None
            if controller is None and initial is not None and (path.parent / 'plan.json').is_file():
                controller = register_control(path, initial.environ)
                self._owned[str(path)] = controller
            return controller

    def close(self):
        with self._guard:
            owned, self._owned = self._owned, {}
        for controller in owned.values():
            controller.close()

"""Publish a fresh Suite and its cleanup protection before any Agent dispatch."""

from agentbench.cli.history import PROJECT_ROOT
from agentbench.harness.session import SuiteStore
from agentbench.harness.session.references import history_guard, register_suite_reference

from .log import SuiteResultLog
from agentbench.cli.result_paths import legacy_results_parent, validate_results_dir


def begin_result_log(output_path, suite_id, agents, *, configuration, environ, results_dir=None):
    """Return a writer for a new indexed Suite, closing it if indexing fails.

    ``results_dir`` explicitly selects the result root, including missing or
    dotted directory names. ``output_path`` retains legacy naming-base rules.
    ``agents`` and ``configuration`` are frozen into its plan.
    ``environ`` supplies the existing secret redaction
    context. The caller owns the returned writer and must close it after the run.
    """
    parent = validate_results_dir(output_path, results_dir)
    if parent is None:
        if output_path is None:
            raise ValueError('A result directory or legacy output path is required')
        parent = legacy_results_parent(output_path)
    with history_guard(PROJECT_ROOT):
        store = SuiteStore.begin(parent / 'suites', suite_id, agents,
                                 configuration=configuration, environ=environ,
                                 result_log_path=output_path)
        try:
            register_suite_reference(store.directory, project_root=PROJECT_ROOT)
            return SuiteResultLog(store)
        except BaseException:
            store.close()
            raise

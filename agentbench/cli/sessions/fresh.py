"""Publish a fresh Suite and its cleanup protection before any Agent dispatch."""

from pathlib import Path

from agentbench.cli.history import PROJECT_ROOT
from agentbench.harness.session import SuiteStore
from agentbench.harness.session.references import history_guard, register_suite_reference

from .log import SuiteResultLog


def begin_result_log(output_path, suite_id, agents, *, configuration, environ):
    """Return a writer for a new indexed Suite, closing it if indexing fails.

    ``output_path`` selects the Suite parent; ``agents`` and ``configuration``
    are frozen into its plan. ``environ`` supplies the existing secret redaction
    context. The caller owns the returned writer and must close it after the run.
    """
    with history_guard(PROJECT_ROOT):
        base = Path(output_path).resolve()
        parent = base if not base.suffix and base.is_dir() else base.parent
        store = SuiteStore.begin(parent / 'suites', suite_id, agents,
                                 configuration=configuration, environ=environ,
                                 result_log_path=output_path)
        try:
            register_suite_reference(store.directory, project_root=PROJECT_ROOT)
            return SuiteResultLog(store)
        except BaseException:
            store.close()
            raise

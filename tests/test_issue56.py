"""Issue #56: an ImportError from an SDK runner becomes a selection error, not a traceback."""
import pytest

from agentbench.harness.errors import ProviderSelectionError
from agentbench.sdk.plugins import evaluation_plan
from agentbench.sdk.runtime import build_evaluation_runner
from tests.test_sdk_directory import MINIMAL_PLUGIN, adapter_directory, add_adapter  # noqa: F401 - fixture


def _runner_raising(error):
    return MINIMAL_PLUGIN + f'''
def _broken(**kwargs):
    raise {error}
plugin.create_benchmark_runner = _broken
'''


def test_partially_present_dependency_is_reported_as_a_selection_error(adapter_directory):  # noqa: F811
    # `from kuma import create_run` against a module that lacks the name raises
    # ImportError, which is the parent of ModuleNotFoundError, not a subclass.
    add_adapter(adapter_directory, source=_runner_raising(
        "ImportError(\"cannot import name 'create_run' from 'kuma'\", name='kuma')"))
    with pytest.raises(ProviderSelectionError) as raised:
        build_evaluation_runner(evaluation_plan(), model=None, trace_sink=None, trace_max_bytes=1024)
    assert "import failed: cannot import name 'create_run' from 'kuma'" in str(raised.value)
    assert isinstance(raised.value.__cause__, ImportError)


def test_missing_module_keeps_its_specific_message(adapter_directory):  # noqa: F811
    add_adapter(adapter_directory, source=_runner_raising(
        "ModuleNotFoundError(\"No module named 'kuma'\", name='kuma')"))
    with pytest.raises(ProviderSelectionError, match="missing module 'kuma'"):
        build_evaluation_runner(evaluation_plan(), model=None, trace_sink=None, trace_max_bytes=1024)


def test_other_runner_errors_are_not_relabelled(adapter_directory):  # noqa: F811
    add_adapter(adapter_directory, source=_runner_raising("RuntimeError('adapter bug')"))
    with pytest.raises(RuntimeError, match='adapter bug'):
        build_evaluation_runner(evaluation_plan(), model=None, trace_sink=None, trace_max_bytes=1024)

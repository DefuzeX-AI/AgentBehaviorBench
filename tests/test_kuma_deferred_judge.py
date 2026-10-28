"""Host Judge dependency prerequisites. Deferred-evidence coverage is postponed."""
import pytest


@pytest.mark.parametrize('installed', ['0.3.2', None])
def test_host_sdk_dependency_is_checked_before_case_work(installed, monkeypatch):
    from importlib.metadata import PackageNotFoundError
    from agentbench.sdk.plugin.kuma.configuration import validate_host_judge_dependency
    def version(_):
        if installed is None:
            raise PackageNotFoundError('kuma-defuzex')
        return installed
    monkeypatch.setattr('importlib.metadata.version', version)
    with pytest.raises(ValueError, match='Host Judge requires'):
        validate_host_judge_dependency()

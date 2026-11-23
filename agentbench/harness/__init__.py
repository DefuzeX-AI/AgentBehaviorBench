"""Benchmark orchestration helpers, loaded only by their callers."""
from importlib import import_module

_EXPORTS = {
    'AgentInvocationError': '.errors',
    'AgentNotRunningError': '.errors',
    'AgentRegistration': '.registry',
    'AgentRegistry': '.registry',
    'AgentRunner': '.runner',
    'AgentStartError': '.errors',
    'BenchmarkProgress': '.progress',
    'BenchmarkResult': '.result',
    'BenchmarkRunner': '.runner',
    'BenchmarkStepFailure': '.result',
    'BenchmarkStepResult': '.result',
    'BenchmarkSuiteResult': '.result',
    'CaseResult': '.result',
    'ConcurrencyConfigurationError': '.concurrency',
    'ConcurrencySettings': '.concurrency',
    'EvaluationFailure': '.result',
    'EvaluationRunner': 'agentbench.sdk.contracts',
    'ProgressCallback': '.progress',
    'ProviderSelectionError': '.errors',
    'RunningAgent': '.runner',
    'SDK': 'agentbench.sdk.contracts',
    'SDKReport': 'agentbench.sdk.contracts',
    'SDKRun': 'agentbench.sdk.contracts',
    'SDKRunFactory': 'agentbench.sdk.contracts',
    'SDKTestInput': 'agentbench.sdk.contracts',
    'SuiteAgentResult': '.result',
    'SuiteConfigurationError': '.errors',
    'SuiteRunner': '.runner',
    'load_registry': '.registry',
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name], __name__), name)
    globals()[name] = value
    return value

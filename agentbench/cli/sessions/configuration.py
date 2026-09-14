"""Capture reconstructible, non-secret runner options for a saved Suite."""

from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re

from agentbench.harness.concurrency import ConcurrencySettings
from agentbench.harness.scheduling import RetryPolicy
from agentbench.sdk.plugins import resolve_sdk


def runner_configuration(runner):
    """Return public options for directory plugins, or None for injected objects."""
    factory = getattr(runner, '_runner_factory', None)
    plan = getattr(factory, 'plan', None)
    reference = getattr(getattr(plan, 'selection', None), 'reference', None)
    if reference is None or reference.source != 'directory':
        return None
    from agentbench.runtime.interception.providers import (
        OPENROUTER_BASE_URL_ENV, DEFAULT_OPENROUTER_BASE_URL)
    from agentbench.harness.session.plan import source_digest
    return {'sdk': reference.name, 'sdk_options': dict(plan.options),
            'model': factory.model or factory.environ.get('OPENROUTER_MODEL'),
            'trace_max_bytes': factory.trace_max_bytes,
            'workers': runner.concurrency.max_parallel_cases,
            'retry_policy': asdict(runner.retry_policy),
            'sdk_distributions': installed_sdk_distributions(reference),
            'provider_base_url': factory.environ.get(OPENROUTER_BASE_URL_ENV, DEFAULT_OPENROUTER_BASE_URL),
            'runtime_source_sha256': source_digest(Path(__file__).resolve().parents[2])}


def installed_sdk_distributions(reference):
    """Read host-installed versions for the selected adapter's declared PyPI dependencies.

    Package metadata is inspected without importing the SDK. Requirements remain
    owned by the plugin; no distribution or import-package name is assumed here.
    Missing host packages use None, since container-only SDKs can be valid too.
    The runtime source fingerprint also covers the original requirements files.
    """
    from agentbench.sdk.discovery import SDK_ROOT
    directory = (SDK_ROOT / reference.name).resolve()
    if directory.parent != SDK_ROOT.resolve():
        raise ValueError('SDK requirements directory is outside the plugin root')
    requirements = directory / 'requirements.txt'
    if not requirements.is_file():
        return {}
    distributions = {}
    for line in requirements.read_text(encoding='utf-8').split('\n'):
        match = re.match(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?(?=\s*(?:[<=>!~;@#]|$))', line)
        if match is None:
            continue
        name = re.sub(r'[-_.]+', '-', match[1]).lower()
        try:
            distributions[name] = version(name)
        except PackageNotFoundError:
            distributions[name] = None
    return dict(sorted(distributions.items()))


def build_saved_runner(configuration, environ, *, activity_sink=None):
    """Reconstruct a directory SDK runner without putting credentials in a plan."""
    from agentbench.cli.trace_runtime import build_trace_suite_runner
    runner = build_trace_suite_runner(
        max_bytes=configuration['trace_max_bytes'], model=configuration.get('model'),
        sdk_selection=resolve_sdk(configuration['sdk']), sdk_options=configuration.get('sdk_options'),
        concurrency=ConcurrencySettings(configuration['workers']), environ=environ,
        activity_sink=activity_sink)
    runner.retry_policy = RetryPolicy(**configuration.get('retry_policy', {}))
    return runner


def resolve_suite(value, root=None):
    """Accept a canonical directory, its events file, or an ID under results/suites."""
    path = Path(value)
    if path.is_file():
        path = path.parent
    if path.is_dir() and (path / 'plan.json').is_file():
        return path.resolve()
    base = Path(root) if root is not None else Path.cwd() / 'results' / 'suites'
    from agentbench.harness.session.plan import validate_suite_id
    return (base / validate_suite_id(str(value))).resolve()

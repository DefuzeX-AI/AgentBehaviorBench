"""SDK-neutral discovery checks and public, timestamped viewer snapshots."""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
from .contracts import SDKStrategyChecks, SDKVersionInfo, StrategyCheck


class StrategyChecks(dict):
    """Per-Agent results plus optional SDK-wide display metadata."""
    sdk_info = None


def snapshot_path(root, unit):
    key = hashlib.sha256(str(Path(unit).resolve()).encode()).hexdigest()
    return Path(root) / 'cache/strategy-checks' / (key + '.json')


def check_agents(agents, *, selection=None, sdk=None, environ=None, root=None, timeout=10):
    from .plugins import resolve_sdk
    from agentbench.project import project_root
    from agentbench.observe.store import atomic_json
    root = Path(root) if root else project_root()
    if selection is None and sdk is None:
        selection = resolve_sdk()
    plugin = sdk if sdk is not None else selection.value
    sdk_name = selection.reference.name if selection else type(plugin).__name__
    results = StrategyChecks()
    if isinstance(plugin, SDKVersionInfo):
        try:
            results.sdk_info = plugin.version_info()
        except Exception:
            pass  # Version discovery must never prevent Agent discovery.
    supported = isinstance(plugin, SDKStrategyChecks)
    checker = None
    if supported:
        try:
            checker = plugin.strategy_checker(environ=os.environ if environ is None else environ, timeout=timeout)
        except Exception:
            pass  # Do not expose provider errors or credentials in discovery.
    for agent in agents:
        fingerprint = None
        try:
            fingerprint = hashlib.sha256((agent.path / 'requirement.md').read_bytes()).hexdigest()
            if not supported:
                result = StrategyCheck('unsupported', reason='Selected SDK does not provide strategy checks.')
            else:
                try:
                    declared = plugin.strategy_selection(agent.path)
                except ImportError:
                    result = StrategyCheck('unverified', reason='SDK dependencies unavailable.')
                except Exception:
                    result = StrategyCheck('invalid', reason='Invalid Agent profile or Strategy Group declaration.')
                else:
                    if declared is None:
                        result = StrategyCheck('unverified', reason='No explicit selection; SDK default applies.')
                    elif checker is None:
                        result = StrategyCheck('unverified', *declared, reason='Could not refresh the SDK catalog; check credentials and connection.')
                    else:
                        result = checker.strategies_check(*declared)
        except Exception:
            result = StrategyCheck('unverified', reason='Strategy check could not be completed.')
        results[agent.agent_id] = asdict(result)
        if fingerprint:
            try:
                destination = snapshot_path(root, agent.path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                atomic_json(destination, {**asdict(result), 'sdk': sdk_name,
                    'checked_at': datetime.now(timezone.utc).isoformat(), 'profile_sha256': fingerprint})
            except OSError:
                pass  # A cache permission problem must not prevent discovery.
    return results

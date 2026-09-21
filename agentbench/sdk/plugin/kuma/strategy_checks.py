"""KUMA Strategy Group ID/version checks against one official catalog."""
from agentbench.sdk.contracts import StrategyCheck


class KumaStrategyChecker:
    def __init__(self, catalog):
        self.catalog = catalog

    def strategies_check(self, strategy_id, version=None):
        groups = [g for g in self.catalog['groups'] if g['id'] == strategy_id
                  and (version is None or g['version'] == version)]
        release = self.catalog.get('catalog_release')
        if len(groups) != 1:
            return StrategyCheck('invalid', strategy_id, version, reason='Unknown ID/version or ambiguous version.', catalog_release=release)
        group = groups[0]
        return StrategyCheck('valid' if group['available'] else 'invalid', strategy_id, group['version'],
                             group['display_name'], '' if group['available'] else 'Strategy Group is unavailable.', release)


def selection(directory):
    from kuma.repository.agent_profiles import parse_agent_profile
    profile = parse_agent_profile(directory / 'requirement.md')
    group = profile.strategy_group
    return (group.id, group.version) if group else None


def checker(*, environ, timeout):
    from .onboarding_catalog import fetch
    return KumaStrategyChecker(fetch(environ=environ, timeout=timeout)['strategy_group_catalog'])

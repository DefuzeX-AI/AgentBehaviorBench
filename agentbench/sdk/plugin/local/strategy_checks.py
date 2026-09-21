"""Preserve declared strategy identity without claiming online validation."""
from agentbench.sdk.contracts import StrategyCheck


class LocalStrategyChecker:
    def strategies_check(self, strategy_id, version=None):
        return StrategyCheck(
            'unverified', strategy_id, version,
            reason='Local SDK does not provide catalog validation.',
        )

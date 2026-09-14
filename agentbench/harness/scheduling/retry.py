"""Provider-neutral retry budgets; SDK adapters decide what is recoverable."""

from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class RetryPolicy:
    """Bound Case retries independently of an SDK's HTTP request budget.

    Args:
        max_retries: Extra automatic attempts after the initial attempt.
        initial_delay: First backoff in seconds; zero allows deterministic tests.
        multiplier: Exponential growth of subsequent delays.
        maximum_delay: Upper bound for backoff seconds.
        jitter: Fractional random spread, between zero and one.
    """

    max_retries: int = 2
    initial_delay: float = 5.0
    multiplier: float = 3.0
    maximum_delay: float = 60.0
    jitter: float = 0.1

    def __post_init__(self):
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError('max_retries must be a nonnegative integer')
        for name in ('initial_delay', 'multiplier', 'maximum_delay', 'jitter'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be a finite nonnegative number')
        if self.multiplier < 1 or self.jitter > 1:
            raise ValueError('multiplier must be at least one and jitter at most one')

    def permits(self, result, retries_used):
        """Only honor explicit safe adapter decisions, never verdict strings."""
        recovery = (result.artifacts or {}).get('recovery', {})
        return (result.benchmark is None and result.status == 'failed'
                and retries_used < self.max_retries
                and recovery.get('automatic') is True
                and recovery.get('action') in {'replay_case', 'resume_request'})

    def delay(self, retry_number):
        base = min(self.maximum_delay, self.initial_delay * self.multiplier ** min(retry_number - 1, 32))
        return min(self.maximum_delay, max(0.0, base * random.uniform(1 - self.jitter, 1 + self.jitter)))

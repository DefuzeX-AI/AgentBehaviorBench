"""Shared CLI options for the harness's bounded Case retry policy."""

from dataclasses import replace
from agentbench.harness.scheduling import RetryPolicy


def configure_retry_parser(parser):
    parser.add_argument('--case-retries', type=int,
                        help='Maximum extra attempts for safe transient Case failures; 0 disables them.')
    parser.add_argument('--retry-delay', type=float, help='Initial Case retry backoff in seconds.')


def retry_policy_argument(args):
    """Return an explicit policy override, or None to preserve the runner default."""
    changes = {field: getattr(args, argument) for argument, field in
               (('case_retries', 'max_retries'), ('retry_delay', 'initial_delay'))
               if getattr(args, argument, None) is not None}
    return replace(RetryPolicy(), **changes) if changes else None

"""Artifact layouts recorded in a saved Suite plan.

Both layouts keep Cases under ``agents/<agent_id>/cases/<slot>/attempts/<id>``.
v1 names each Case slot with 32 hex digits. v2 uses 8 digits to keep Windows
paths short; each v2 slot records its owner, and a taken name moves on to the
next candidate. Saved v1 Suites keep resolving their original directories.
"""

AGENT_ATTEMPTS_V1 = 'agent-attempts-v1'
AGENT_ATTEMPTS_V2 = 'agent-attempts-v2'
CURRENT_LAYOUT = AGENT_ATTEMPTS_V2
MANAGED_LAYOUTS = frozenset({AGENT_ATTEMPTS_V1, AGENT_ATTEMPTS_V2})


def is_managed(plan):
    """True for Suites whose artifacts live in the Agent-owned layout."""
    return isinstance(plan, dict) and plan.get('artifact_layout') in MANAGED_LAYOUTS

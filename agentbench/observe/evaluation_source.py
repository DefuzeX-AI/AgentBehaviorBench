"""Public evaluator identity from saved Suite configuration and execution records.

The evaluated Agent and its framework adapter are not the evaluation SDK. In
particular, both Local and KUMA have historically saved ``container-sdk`` as the
adapter name. Never use that field, Case IDs, paths, or current CLI defaults to
label old results.
"""

import re


# These are the persisted execution modes of the existing SDK plugins. Unknown
# modes are retained as evidence, but do not identify an SDK by themselves.
LEGACY_MODE_SDK = {'official-container': 'kuma', 'local-container': 'local'}


def _identifier(value):
    """Keep bounded identity fields only; exclude URLs, options and credentials."""
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.:-]{0,119}', value):
        return value.lower() if value.lower() in {'kuma', 'local'} else value
    return None


def evaluation_source(snapshot, plan=None):
    """Summarize recorded evaluators without masking mixed historical records.

An immutable plan identifies the selected SDK even before any Case completes.
For legacy results without a plan, known persisted provider modes identify the
runtime. A partial legacy record does not assert that every Case used that SDK.
Conflicting plan/runtime identities remain visible instead of choosing one.
"""
    configuration = (plan or {}).get('configuration') or {}
    configured = _identifier(configuration.get('sdk')) if isinstance(configuration, dict) else None
    observed, modes = set(), set()
    missing = False
    for job in snapshot.get('jobs', []):
        for case in job.get('cases', []):
            results = [attempt.get('result') for attempt in case.get('attempts', [])
                       if isinstance(attempt, dict)]
            results.append(case.get('result'))
            recorded = False
            for result in results:
                if not isinstance(result, dict):
                    continue
                benchmark = (result or {}).get('benchmark') or {}
                if not isinstance(benchmark, dict):
                    continue
                mode = _identifier(benchmark.get('provider_mode'))
                if mode:
                    modes.add(mode)
                    sdk = LEGACY_MODE_SDK.get(mode)
                    if sdk:
                        observed.add(sdk)
                        recorded = True
                    else:
                        missing = True
                else:
                    missing = True
            missing |= not recorded
    # A custom SDK may reuse a plugin's execution mode. Its explicit saved name
    # takes precedence; a legacy mode is not grounds to rename that custom SDK.
    identities = ([configured] if configured and configured not in LEGACY_MODE_SDK.values()
                  else sorted(observed | ({configured} if configured else set())))
    status = ('mixed' if len(identities) > 1 else
              'not_recorded' if not identities else
              'partial' if not configured and missing else 'recorded')
    evidence = ('plan_and_results' if configured and modes else 'plan' if configured else
                'results' if modes else 'none')
    return {'schema': 'abb.evaluation.source.v1', 'status': status,
            'sdk': identities[0] if len(identities) == 1 else None,
            'sdks': identities, 'configured_sdk': configured,
            'provider_modes': sorted(modes), 'evidence': evidence}

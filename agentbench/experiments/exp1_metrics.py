"""Detection prefixes use frozen test order and the complete selected Issue set."""

KS = (1, 5, 10, 20, 50)


def summarize(issues, budget):
    count = len(issues)
    metrics = {}
    for k in KS:
        hit = pending = 0
        if k > budget:
            metrics[f'Detection@{k}'] = {'value': None, 'status': 'outside_budget', 'issues': count}
            continue
        for issue in issues:
            prefix = issue['tests'][:k]
            if any(t['hit'] is True for t in prefix):
                hit += 1
            elif len(prefix) < k or any(t['hit'] is None for t in prefix):
                pending += 1
        metrics[f'Detection@{k}'] = {
            'value': hit / count if count and not pending else None,
            'status': 'complete' if count and not pending else 'pending',
            'hit_issues': hit, 'pending_issues': pending, 'issues': count,
            'bounds': [hit / count, (hit + pending) / count] if count else None}
    return metrics

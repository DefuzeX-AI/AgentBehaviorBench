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


def summarize_rounds(rows):
    """Detection within a round is existential; missing evidence stays unknown."""
    groups = {}
    for row in rows:
        groups.setdefault(row['round_index'], []).append(row)
    result = []
    for number, members in sorted(groups.items()):
        hit = (True if any(r['hit'] is True for r in members) else
               None if any(r['hit'] is None for r in members) else False)
        result.append({'round_index': number, 'hit': hit, 'case_count': len(members),
                       'execution_wall_seconds': sum(r['execution_wall_seconds'] or 0 for r in members)})
    return result


def aggregate(experiments):
    """Combine explicitly selected v2 experiments, retaining every Issue once."""
    identities, issues = set(), []
    for experiment in experiments:
        if experiment.get('schema') != 'abb.exp1.v2' or experiment.get('metrics_unit') != 'case_executions':
            raise ValueError('Only execution-based v2 experiments can be aggregated; read legacy results separately')
        for issue in experiment['issues']:
            identity = (experiment['agent_id'], issue['issue_id'])
            if identity in identities:
                raise ValueError(f'Duplicate Issue in aggregation: {identity[0]} / {identity[1]}')
            identities.add(identity)
            issues.append({**issue, 'agent_id': experiment['agent_id'],
                           'experiment_id': experiment['experiment_id']})
    # Do not improve a score by dropping Issues with smaller declared budgets.
    budget = min(e['budget'] for e in experiments)
    metrics = summarize(issues, budget)
    return {'schema': 'abb.exp1.aggregate.v1', 'metrics_unit': 'case_executions',
            'issue_count': len(issues), 'budget': budget, 'issues': issues, 'metrics': metrics,
            'experiments': [e['directory'] for e in experiments],
            'status': 'partial' if any(e['status'] != 'completed' for e in experiments) else 'completed'}

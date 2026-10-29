"""Read current Issue references without changing the legacy GT/Judge contract."""
from agentbench import trajectory
from .files import read_json, text_field, within
from .manifests import registered_units


def load_issue(root, agent_id, issue_id):
    units, invalid, _ = registered_units(root)
    if agent_id not in units or invalid is None or agent_id in invalid:
        raise ValueError('Agent has no valid registration')
    unit = units[agent_id]
    folder = within(unit, unit / 'ground_truth' / issue_id)
    document = read_json(within(folder, folder / 'verify.case.json'))
    issue = document.get('issue')
    if not isinstance(issue, dict) or type(issue.get('number')) is not int:
        raise ValueError('Issue reference requires issue.number')
    if issue_id != f"issue_{issue['number']}":
        raise ValueError('Issue reference identity differs from Case folder')
    for field in ('expected', 'defect'):
        text_field(document, field)
    references = []
    for path in sorted((folder / 'runs').glob('*/trajectory/*/trajectory.json')):
        path = within(folder, path)
        value = trajectory.read(path.parent)
        if value is None or value.get('status') == 'failed' or not value.get('steps'):
            raise ValueError(f'{issue_id}: unusable reference trajectory')
        if value.get('agent_id') != agent_id:
            raise ValueError(f'{issue_id}: reference trajectory belongs to another Agent')
        references.append({**value, 'attempt': path.parent.relative_to(folder).as_posix()})
    if not references:
        raise ValueError(f'{issue_id}: no saved reference trajectory under runs/*/trajectory/*')
    return {'agent_id': agent_id, 'issue_id': issue_id,
            'definition': {key: document.get(key) for key in
                           ('issue', 'expected', 'defect', 'Root cause', 'commit_version')},
            'trajectories': references}

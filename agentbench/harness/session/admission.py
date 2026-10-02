"""Append-only admission of saved Cases into a linked Suite."""

from copy import deepcopy
from dataclasses import replace

from .cases import retain_prepared, verify_prepared
from .codec import json_value, prepared_from_json
from .plan import SuiteProvenanceError, digest_json


def agent_identity(record):
    return {key: value for key, value in record.items() if key != 'case_count'}


def extend_plan(plan, event):
    """Project admissions without rewriting the original plan or its provenance."""
    if event.get('event') != 'suite_cases_added':
        return plan
    if not plan.get('origin_suite_id'):
        raise ValueError('Only linked reuse Suites accept additional saved Cases')
    result = deepcopy(plan)
    agents = {agent['agent_id']: agent for agent in result['agents']}
    counts = {key: value['case_count'] for key, value in agents.items()}
    for record in event['agents']:
        identifier = record['agent_id']
        if identifier in agents:
            if agent_identity(record) != agent_identity(agents[identifier]):
                raise SuiteProvenanceError('Added Agent source or settings differ from this Suite')
        else:
            agents[identifier] = deepcopy(record)
            result['agents'].append(agents[identifier])
            counts[identifier] = 0
    if not event['cases']:
        raise ValueError('A reuse admission requires saved Cases')
    for entry in event['cases']:
        identifier, saved = entry['agent_id'], entry['prepared_case']
        if identifier not in agents or saved['case_index'] != counts[identifier]:
            raise ValueError('Added Cases must occupy new consecutive slots')
        if not saved.get('artifact_path') or not saved.get('artifact_sha256') or not entry.get('origin'):
            raise ValueError('Added Cases require retained artifacts and origin')
        counts[identifier] += 1
    for identifier, count in counts.items():
        agents[identifier]['case_count'] = count
    result['provenance_sha256'] = digest_json({key: result[key] for key in ('agents', 'configuration')})
    return result


def admit_reuse_request(store, request):
    """Publish all slots of a request atomically; a replay returns the original slots."""
    for event in store.events:
        if event.get('event') == 'suite_cases_added' and event.get('reuse_request_id') == request['request_id']:
            return [(entry['agent_id'], entry['prepared_case']['case_index']) for entry in event['cases']]
    counts = {agent.agent_id: agent.case_count for agent in store.registrations}
    entries = []
    for entry in request['cases']:
        identifier = entry['agent_id']
        index = counts.get(identifier, 0)
        case = verify_prepared(prepared_from_json(entry['prepared_case']))
        retained = retain_prepared(store.directory, identifier, replace(case, case_index=index))
        entries.append({**entry, 'prepared_case': json_value(retained)})
        counts[identifier] = index + 1
    event = {'event': 'suite_cases_added', 'reuse_request_id': request['request_id'],
             'agents': request['agents'], 'cases': entries}
    extend_plan(store.plan, event)  # Validate before publishing any new slot.
    store.append(event)
    return [(entry['agent_id'], entry['prepared_case']['case_index']) for entry in entries]

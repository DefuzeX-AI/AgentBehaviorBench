"""Assemble the flat step sequence for one attempt directory.

A step is one model call with the tool executions it emitted, or one tool
execution no model call emitted. Framework chain and middleware spans are not
steps; their payloads remain in the raw evidence.
"""
import hashlib
from collections import defaultdict
from pathlib import Path

from agentbench.observe.interactions import load_index
from agentbench.observe.view_api import RunViewAPI

from .actors import actor_for, langgraph_actor
from .content import bounded, digest, framework_input, framework_output, max_value_bytes, model_input, model_output
from .files import file_changes, replay_events
from .metadata import build_metadata
from .schema import BUILDER_VERSION, SCHEMA
from .sources import _data, framework_calls, llm_record, node_tool_calls, order_key, tool_log, tool_rows, wire_calls


def _identity(api, run):
    request = None
    for folder in api.outputs():
        request = api.read(f'{folder}/request.json') or api.read(f'{folder}/invocation.json')
        if request:
            break
    request = request or {}
    context = request.get('observation_context') if isinstance(request.get('observation_context'), dict) else {}
    return {'agent_id': run.get('agent_id') or request.get('agent_id'),
            'framework': request.get('framework') or run.get('framework') or 'unknown',
            'case_id': run.get('case_id') or context.get('case_id')}


def _ordinal(folder):
    return folder.rsplit('/', 1)[-1] if folder else None


def _sources(index, api):
    from agentbench.observe.artifact_paths import canonical_relative
    sources = []
    for name, _, _ in index_files(index):
        try:
            sources.append({'path': canonical_relative(name),
                            'sha256': hashlib.sha256(api.file(name).read_bytes()).hexdigest()})
        except (FileNotFoundError, OSError, ValueError):
            continue
    try:
        path = api.file('replay/events.jsonl')
        sources.append({'path': 'replay/events.jsonl', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    except FileNotFoundError:
        pass
    return sources


def index_files(index):
    from agentbench.observe.interactions import _files
    return _files(index.root)


def _recover_tool_calls(index, output, start):
    if not output.get('tool_calls'):
        calls = node_tool_calls(index, start.get('parent_span_id'))
        if calls:
            output['tool_calls'] = calls
            output['tool_calls_source'] = 'graph_node'
    return output


def _model_step(index, entry, agent_id, limit):
    wire, framework = entry['wire'], entry['framework']
    if wire is not None:
        request, response = _data(wire.get('_request')), _data(wire.get('_response'))
        payload_in = request.get('payload')
        model_in = model_input(payload_in)
        output_source = 'wire'
        if wire.get('_response') is not None and 'payload' in response:
            output = model_output(response.get('payload'))
        else:
            error = next((_data(r) for r in reversed(entry['records']) if 'error' in (r['raw'].get('event') or '')), {})
            wire_error = {k: error.get(k) for k in ('error_code', 'error', 'message', 'upstream_status', 'local_status')
                          if error.get(k) is not None}
            end = _data(llm_record(wire, 'span_end')) if framework is not None else {}
            if end.get('output') is not None:
                # The wire record failed, but the framework still received a result.
                output, output_source = framework_output(end['output']), 'framework'
                output = _recover_tool_calls(index, output, _data(llm_record(wire, 'span_start')))
            else:
                output = {'text': None, 'reasoning': None, 'tool_calls': [], 'finish_reason': None, 'usage': None,
                          'model': request.get('model')}
            output['wire_error'] = wire_error
        step = {'kind': 'model', 'source': 'wire+framework' if framework is not None else 'wire',
                'output_source': output_source,
                'agent_name': actor_for(agent_id, llm_record(wire, 'span_start')) if framework is not None else agent_id,
                'started_at': wire.get('timestamp'), 'ended_at': wire.get('ended'),
                'model': output.get('model') or request.get('model') or payload_in.get('model') if isinstance(payload_in, dict) else request.get('model'),
                'purpose': wire.get('purpose'), 'status': wire.get('status'),
                'input': bounded(model_in, limit), 'output': bounded(output, limit),
                'evidence': {'interaction_id': wire['id'], 'call_id': wire.get('call_id'),
                             'framework_span_id': wire.get('framework_span_id'),
                             'request_sha256': digest(payload_in), 'response_sha256': digest(response.get('payload'))}}
        return step, [c.get('id') for c in output.get('tool_calls') or [] if c.get('id')]
    start, end = _data(framework.get('_request')), _data(framework.get('_response'))
    output = _recover_tool_calls(index, framework_output(end.get('output')), start)
    step = {'kind': 'model', 'source': 'framework',
            'agent_name': langgraph_actor(agent_id, start.get('metadata')),
            'started_at': framework.get('timestamp'), 'ended_at': framework.get('ended'),
            'model': output.get('model') or start.get('name'), 'purpose': 'unknown', 'status': framework.get('status'),
            'input': bounded(framework_input(start.get('input')), limit), 'output': bounded(output, limit),
            'evidence': {'interaction_id': framework['id'], 'call_id': None,
                         'framework_span_id': framework.get('framework_span_id'),
                         'request_sha256': digest(start.get('input')), 'response_sha256': digest(end.get('output'))}}
    return step, [c.get('id') for c in output.get('tool_calls') or [] if c.get('id')]


def build(directory, *, environ=None, project_root=None):
    root = Path(directory).resolve()
    api = RunViewAPI(root)
    index = load_index(root)
    limit = max_value_bytes(environ)
    run = api.read('run.json') or {}
    identity = _identity(api, run)
    agent_id = identity['agent_id'] or 'unknown'
    warnings = list(index.warnings)
    folders = [f for f in api.outputs()]
    only_folder = folders[0] if len(folders) == 1 else None

    tools = tool_rows(index)
    tools_by_call = defaultdict(list)
    for row in tools:
        if row.get('tool_call_id'):
            tools_by_call[row['tool_call_id']].append(row)
    framework_by_span = {row.get('framework_span_id'): row for row in framework_calls(index) if row.get('framework_span_id')}

    entries, consumed = [], set()
    for row in wire_calls(index):
        framework = framework_by_span.get(row.get('framework_span_id'))
        if framework is not None:
            consumed.add(framework['id'])
        entries.append({'wire': row, 'framework': framework, 'records': index.groups.get(row['id'], []),
                        'folder': row.get('_context') or (framework or {}).get('_context'), 'order': order_key(row)})
    for row in framework_calls(index):
        if row['id'] not in consumed:
            entries.append({'wire': None, 'framework': row, 'records': index.groups.get(row['id'], []),
                            'folder': row.get('_context'), 'order': order_key(row)})

    used, ambiguous, steps = set(), 0, []
    for entry in entries:
        step, emitted = _model_step(index, entry, agent_id, limit)
        folder = entry['folder'] or only_folder
        logs = []
        for call_id in emitted:
            candidates = [t for t in tools_by_call.get(call_id, [])
                          if not folder or not t.get('_context') or t['_context'] == folder]
            if len(candidates) == 1:
                log = tool_log(index, candidates[0]); log['link'] = 'exact'; used.add(candidates[0]['id'])
            elif candidates:
                log = tool_log(index, candidates[0]); log['link'] = 'ambiguous'; ambiguous += 1
                log['evidence']['candidates'] = [t['id'] for t in candidates]
                used.update(t['id'] for t in candidates)
            else:
                log = {'tool_call_id': call_id, 'tool_name': next((c.get('name') for c in step['output'].get('tool_calls') or []
                       if c.get('id') == call_id), None) or 'unknown', 'input_arguments': next((c.get('arguments') for c in
                       step['output'].get('tool_calls') or [] if c.get('id') == call_id), None), 'outputs': None,
                       'execution_status': 'not_observed', 'exit_status': None, 'link': 'none', 'evidence': {}}
                warnings.append(f"tool call {call_id} was emitted but its execution was not observed")
            logs.append(bounded(log, limit))
        if entry['folder'] is None and only_folder is None and folders:
            warnings.append(f"model call {step['evidence']['interaction_id']} could not be assigned to an Input")
        steps.append({**step, 'input_ordinal': _ordinal(folder), 'tool_logs': logs, 'order': entry['order']})
    for row in tools:
        if row['id'] in used:
            continue
        log = tool_log(index, row); log['link'] = 'none'
        folder = row.get('_context') or only_folder
        start = _data(row.get('_request'))
        steps.append({'kind': 'tool_only', 'source': 'framework', 'agent_name': langgraph_actor(agent_id, start.get('metadata')),
                      'started_at': row.get('timestamp'), 'ended_at': row.get('ended'), 'status': row.get('status'),
                      'input_ordinal': _ordinal(folder), 'tool_logs': [bounded(log, limit)], 'order': order_key(row)})
    steps.sort(key=lambda s: s['order'])
    for number, step in enumerate(steps, 1):
        step.pop('order'); step['step_id'] = number
        step_order = ['step_id', 'input_ordinal', 'agent_name', 'kind', 'source', 'started_at', 'ended_at']
        for key in reversed(step_order):
            step[key] = step.pop(key)
        for key in step_order:
            step[key] = step.pop(key)
        for key in list(step):
            if key not in step_order:
                step[key] = step.pop(key)

    replays = replay_events(api)
    inputs, file_coverage = [], set()
    for folder in folders:
        ordinal = _ordinal(folder)
        ids = [s['step_id'] for s in steps if s['input_ordinal'] == ordinal]
        result = api.read(f'{folder}/result.json') or {}
        record = api.read(f'{folder}/input.json') or {}
        changes, coverage = file_changes(api, folder, replays)
        file_coverage.add(coverage)
        inputs.append({'ordinal': ordinal, 'input_id': record.get('input_id'),
                       'prompt': bounded(record.get('payload'), limit),
                       'step_range': [ids[0], ids[-1]] if ids else None,
                       'result': bounded({'status': result.get('status'), 'output': result.get('output'),
                                          'error_type': result.get('error_type'), 'error': result.get('error')}, limit),
                       'file_changes': bounded(changes, limit)})

    actors = sorted({s['agent_name'] for s in steps} | {agent_id})
    first_input = next((s['input'] for s in steps if s['kind'] == 'model'), None)
    metadata, notes = build_metadata(api, agent_id=agent_id, framework=identity['framework'], first_input=first_input,
                                     actors=actors, project_root=project_root)
    # Missing unit references limit context, not the step evidence itself.
    metadata['notes'] = notes
    sources = {s.get('source') for s in steps if s['kind'] == 'model'}
    model_coverage = ('wire+framework' if 'wire+framework' in sources else 'wire' if 'wire' in sources
                      else 'framework' if 'framework' in sources else 'not_observed')
    acp = any(api.read(f'{folder}/acp-summary.json') for folder in folders)
    tool_coverage = 'acp' if acp else 'framework' if tools else 'not_observed'
    files_coverage = next((c for c in ('diff', 'replay', 'skipped', 'not_observed') if c in file_coverage), 'not_observed')
    unlinked = sum(s['kind'] == 'tool_only' for s in steps)
    not_observed = sum(log['execution_status'] == 'not_observed' for s in steps for log in s['tool_logs'])
    value = {'schema': SCHEMA, 'builder_version': BUILDER_VERSION,
             'status': 'partial' if warnings or not_observed or not steps else 'complete',
             'run_id': run.get('run_id') or root.name, 'agent_id': agent_id,
             'case_id': identity['case_id'], 'framework': identity['framework'],
             'metadata': bounded(metadata, limit), 'steps': steps, 'inputs': inputs,
             'coverage': {'model_calls': model_coverage, 'tool_calls': tool_coverage, 'file_changes': files_coverage,
                          'ambiguous_links': ambiguous, 'unlinked_tool_calls': unlinked,
                          'unobserved_tool_executions': not_observed},
             'sources': _sources(index, api), 'warnings': warnings}
    return value

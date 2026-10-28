"""Render a trajectory for a model reader, in the three modes TraceElephant uses.

``full`` keeps every step's request and response. ``truncate_middle`` keeps the
head and tail of oversized requests only. ``response_only`` drops requests.
The stored trajectory is never modified by rendering.
"""
import json

MODES = ('full', 'truncate_middle', 'response_only')
MAX_REQUEST_CHARS = 3000


def _dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=None, default=str)


def _truncate_middle(text, limit=MAX_REQUEST_CHARS):
    if len(text) <= limit:
        return text
    half = limit // 2
    return '[TRUNCATED] ' + text[:half] + '\n...[truncated middle content]...\n' + text[-half:]


def render_step(step, mode='full'):
    if mode not in MODES:
        raise ValueError('Unknown render mode')
    body = {}
    if step.get('kind') == 'model':
        if mode == 'full':
            body['request'] = step.get('input')
        elif mode == 'truncate_middle':
            body['request'] = _truncate_middle(_dumps(step.get('input')))
        body['response'] = step.get('output')
    if step.get('tool_logs'):
        body['tool_logs'] = [{key: log.get(key) for key in
                              ('tool_name', 'input_arguments', 'outputs', 'execution_status', 'exit_status')}
                             for log in step['tool_logs']]
    return f"Step {step['step_id']} - {step['agent_name']} [{step.get('kind')}]: {_dumps(body)}"


def render_header(trajectory):
    metadata = trajectory.get('metadata') or {}
    configuration = metadata.get('agent_configuration') or {}
    tools = [t.get('name') or (t.get('function') or {}).get('name') for t in configuration.get('tools') or []
             if isinstance(t, dict)]
    lines = [f"Agent: {trajectory.get('agent_id')} ({trajectory.get('framework')})",
             f"Task: {_dumps(metadata.get('task_instruction'))}",
             f"Agents: {', '.join(a.get('agent_name', '') for a in configuration.get('agents') or [])}",
             f"Tools: {', '.join(name for name in tools if name)}"]
    for item in trajectory.get('inputs') or []:
        result = item.get('result') or {}
        lines.append(f"Input {item.get('ordinal')} ({item.get('input_id')}): steps {item.get('step_range')}, "
                     f"result {result.get('status')}: {_dumps(result.get('output'))}")
        for change in item.get('file_changes') or []:
            lines.append(f"  file {change.get('change_type')}: {change.get('path')}")
    return '\n'.join(lines)


def render(trajectory, mode='full'):
    parts = [render_header(trajectory)]
    parts.extend(render_step(step, mode) for step in trajectory.get('steps') or [])
    return '\n\n'.join(parts)


def render_within(trajectory, limit_bytes):
    """Try full, then truncate_middle; never fall back to dropping inputs."""
    for mode in ('full', 'truncate_middle'):
        text = render(trajectory, mode)
        if len(text.encode('utf-8')) <= limit_bytes:
            return text, mode
    return None, None

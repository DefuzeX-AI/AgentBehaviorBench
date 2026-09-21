import { needsAttention } from './model.js';

const text = value => String(value ?? '').toLocaleLowerCase();

export function latestTimestamp(item) {
  const attempts = item.attempts || [];
  const candidates = [item.updated_at, item.completed_at, item.started_at,
    ...attempts.flatMap(attempt => [attempt.updated_at, attempt.finished_at, attempt.completed_at, attempt.started_at])];
  const times = candidates.map(value => Date.parse(value)).filter(Number.isFinite);
  return times.length ? Math.max(...times) : 0;
}

export function filterCases(cases, filters) {
  const query = text(filters.query).trim();
  return cases.filter(item => {
    const searchable = [item.agent_id, item.case_id, item.description, item.prompt,
      item.error?.message, item.error, item.recovery_reason, item.execution_status, item.judge_status]
      .map(text).join(' ');
    return (!query || searchable.includes(query))
      && (!filters.agents?.length || filters.agents.includes(item.agent_id))
      && (!filters.statuses?.length || filters.statuses.includes(item.execution_status))
      && (!filters.judges?.length || filters.judges.includes(item.judge_status || 'not_received'))
      && (!filters.attention || needsAttention(item.execution_status))
      && (!filters.retried || item.retry_count > 0 || item.attempts.length > 1);
  });
}

const statusOrder = ['failed', 'exhausted', 'blocked', 'needs_attention', 'interrupted', 'cancelled',
  'retry_wait', 'retrying', 'running', 'judging', 'waiting_judge', 'generating', 'queued', 'pending',
  'pending_generation', 'prepared', 'ready', 'completed', 'succeeded'];

function valueFor(item, field) {
  if (field === 'agent') return text(item.agent_id);
  if (field === 'status') return statusOrder.indexOf(item.execution_status);
  if (field === 'judge') return text(item.judge_status || 'not_received');
  if (field === 'attempts') return item.attempts.length;
  if (field === 'updated') return latestTimestamp(item);
  return `${text(item.agent_id)}\u0000${String(item.case_index).padStart(8, '0')}`;
}

export function sortCases(cases, field = 'case', order = 'ascend') {
  const direction = order === 'descend' ? -1 : 1;
  return [...cases].sort((left, right) => {
    const a = valueFor(left, field), b = valueFor(right, field);
    if (a < b) return -direction;
    if (a > b) return direction;
    return left.key.localeCompare(right.key);
  });
}

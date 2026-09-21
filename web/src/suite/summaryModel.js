import { isComplete } from './model.js';

function time(value) {
  if (typeof value === 'number') return value < 1e12 ? value * 1000 : value;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function attemptDuration(attempt) {
  if (!attempt) return null;
  if (Number.isFinite(attempt.duration_ms)) return attempt.duration_ms;
  if (Number.isFinite(attempt.duration_seconds)) return attempt.duration_seconds * 1000;
  const start = time(attempt.started_at || attempt.started || attempt.dispatched_at);
  const end = time(attempt.finished_at || attempt.completed_at || attempt.updated_at);
  return start != null && end != null && end >= start ? end - start : null;
}

export function agentSummaries(cases, jobs = []) {
  const jobByAgent = new Map(jobs.map(job => [job.agent_id, job]));
  return [...new Set(cases.map(item => item.agent_id))].sort().map(agentId => {
    const items = cases.filter(item => item.agent_id === agentId);
    const completed = items.filter(item => isComplete(item.execution_status)).length;
    const judged = items.filter(item => item.report_received || item.judge_status).length;
    const passed = items.filter(item => item.judge_status === 'pass').length;
    const durations = items.map(item => attemptDuration(item.attempts.at(-1))).filter(Number.isFinite);
    return {
      agent_id: agentId,
      total: items.length,
      completed,
      judged,
      passed,
      pass_rate: judged ? Math.round((passed / judged) * 100) : null,
      completion_rate: items.length ? Math.round((completed / items.length) * 100) : 0,
      average_duration_ms: durations.length ? durations.reduce((sum, value) => sum + value, 0) / durations.length : null,
      status: jobByAgent.get(agentId)?.status || null,
    };
  });
}

export function formatDuration(milliseconds) {
  if (!Number.isFinite(milliseconds)) return 'Time not recorded';
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms avg`;
  if (milliseconds < 60000) return `${(milliseconds / 1000).toFixed(2)} s avg`;
  return `${(milliseconds / 60000).toFixed(1)} min avg`;
}

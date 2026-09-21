// Logical Case identity is independent of the SDK Run created by each attempt.
export const caseKey = (suiteId, agentId, index) => JSON.stringify([suiteId, agentId, index]);

export const executionLabels = {
  pending: 'Pending generation', pending_generation: 'Pending generation', generating: 'Generating', prepared: 'Prepared', ready: 'Prepared', queued: 'Queued',
  running: 'Running', retrying: 'Retrying', judging: 'Waiting for Judge', waiting_judge: 'Waiting for Judge',
  completed: 'Completed', succeeded: 'Completed', retry_wait: 'Temporary failure / retry pending',
  recovering: 'Recovering request', reconciling: 'Reconciling status', interrupted: 'Interrupted',
  blocked: 'Needs attention', needs_attention: 'Needs attention', failed: 'Execution failed', exhausted: 'Retries exhausted',
  cancelled: 'Cancelled', skipped: 'Skipped', unknown: 'Status unavailable',
};
export const phaseLabels = {
  generate: 'Generate Case', case_generation: 'Generate Case', prepare: 'Prepare Case',
  execute: 'Execute Case', benchmark_execution: 'Execute Case / Judge', agent: 'Agent execution',
  judge: 'Judge', recovery: 'Recover request', recover: 'Recover request', completed: 'Complete',
};
export const needsAttention = status => ['blocked', 'needs_attention', 'failed', 'exhausted', 'interrupted', 'cancelled', 'skipped'].includes(status);
export const isActive = status => ['running', 'retrying', 'judging', 'waiting_judge', 'recovering', 'reconciling', 'generating'].includes(status);
export const isComplete = status => ['completed', 'succeeded'].includes(status);

export function reportOf(item) {
  const benchmark = item?.result?.benchmark || item?.benchmark;
  return benchmark?.report || item?.result?.report || item?.report || null;
}

export function executionStatus(item) {
  if (item.execution_status) return item.execution_status;
  // Older results use failed for a valid Judge issue; retain real execution errors.
  if (reportOf(item) && !item.error && !item.error_type && !item.result?.error && !item.result?.error_type
    && item.host_accepted !== false && item.host_acceptance !== false && item.host_acceptance !== 'rejected') return 'completed';
  return item.status || 'unknown';
}

export function normalizeCases(snapshot) {
  const suiteId = snapshot?.suite_id;
  return (snapshot?.jobs || []).flatMap(job => (job.cases || []).map(item => {
    const agentId = item.agent_id || job.agent_id;
    const attempts = Array.isArray(item.attempts) ? item.attempts.map((attempt, index) => ({
      ...attempt, attempt_number: attempt.attempt_number ?? index + 1,
      attempt_id: attempt.attempt_id || attempt.artifact_run_id || `legacy-${index + 1}`,
    })) : item.artifact_run_id ? [{ ...item, attempt_number: 1, attempt_id: item.artifact_run_id }] : [];
    return {
      ...item, suite_id: suiteId, agent_id: agentId,
      key: caseKey(suiteId, agentId, item.case_index), attempts,
      execution_status: executionStatus(item),
      judge_status: item.judge_status || reportOf(item)?.status || null,
      report_received: item.report_received ?? Boolean(reportOf(item) || ['pass', 'issue', 'insufficient_evidence'].includes(item.judge_status)),
    };
  }));
}

export function currentAttempt(item) {
  return item.attempts.find(attempt => attempt.attempt_id === item.active_attempt_id) || item.attempts.at(-1) || null;
}

export function countCases(cases) {
  return cases.reduce((counts, item) => {
    const status = item.execution_status;
    const category = isComplete(status) ? 'completed' : status === 'retry_wait' ? 'retry_wait'
      : needsAttention(status) ? 'attention'
      : isActive(status) ? 'running' : 'queued';
    counts[category] += 1;
    if (item.report_received) counts.reports += 1;
    if (item.host_accepted === true || item.host_acceptance === true || item.host_acceptance === 'accepted') counts.accepted += 1;
    return counts;
  }, { completed: 0, running: 0, retry_wait: 0, attention: 0, queued: 0, reports: 0, accepted: 0 });
}

export function jobProgress(job) {
  const cases = job.cases || [];
  if (!cases.length) return 'No Cases yet';
  let completed = 0;
  const remaining = new Map();
  for (const item of cases) {
    const status = executionStatus(item);
    if (isComplete(status)) completed += 1;
    else remaining.set(status, (remaining.get(status) || 0) + 1);
  }
  return [`Completed ${completed}/${cases.length}`, ...Array.from(remaining,
    ([status, count]) => `${executionLabels[status] || status} ${count}`)].join(' · ');
}

export function errorText(error) {
  if (!error) return '';
  if (typeof error === 'string') return error;
  return [error.code || error.type || error.error_type, error.message].filter(Boolean).join(' · ') || 'No error details provided';
}

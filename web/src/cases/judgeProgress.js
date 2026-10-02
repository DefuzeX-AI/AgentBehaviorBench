export function judgeProgress(item) {
  if (!item || item.report_received || item.judge_status) return null;
  if (!['waiting_judge', 'running', 'retrying', 'reconciling'].includes(item.execution_status)) return null;
  const status = item.judge_delivery_status;
  if (status === 'queued' || item.stage === 'judge_queue') return {
    title: 'Judge queued', description: 'Agent execution has finished. Its Docker resources have been released; the host queue is waiting for a Judge slot.',
  };
  if (status === 'submitting' || item.stage === 'judge') return {
    title: 'Submitting Judge evidence', description: 'The host worker is uploading the original Case and committed evidence through KUMA.',
  };
  if (status === 'judging' || item.stage === 'judge_wait') return {
    title: 'Waiting for Judge report', description: 'KUMA has accepted the request. Evaluation continues without occupying an Agent container.',
  };
  return null;
}

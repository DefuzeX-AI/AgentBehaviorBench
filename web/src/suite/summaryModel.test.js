import test from 'node:test';
import assert from 'node:assert/strict';
import { agentSummaries, attemptDuration, formatDuration } from './summaryModel.js';

test('Agent summaries separate completion from Judge pass rate', () => {
  const cases = [
    { agent_id: 'alpha', execution_status: 'completed', judge_status: 'pass', report_received: true, attempts: [{ started_at: '2026-01-01T00:00:00Z', finished_at: '2026-01-01T00:00:02Z' }] },
    { agent_id: 'alpha', execution_status: 'completed', judge_status: 'issue', report_received: true, attempts: [{ duration_ms: 4000 }] },
    { agent_id: 'alpha', execution_status: 'running', judge_status: null, attempts: [] },
  ];
  assert.deepEqual(agentSummaries(cases, [{ agent_id: 'alpha', status: 'running' }])[0], {
    agent_id: 'alpha', total: 3, completed: 2, judged: 2, passed: 1, pass_rate: 50,
    completion_rate: 67, average_duration_ms: 3000, status: 'running',
  });
});

test('Duration formatting handles measured and missing attempts', () => {
  assert.equal(attemptDuration({ started_at: 100, completed_at: 102 }), 2000);
  assert.equal(formatDuration(4940), '4.94 s avg');
  assert.equal(formatDuration(null), 'Time not recorded');
});

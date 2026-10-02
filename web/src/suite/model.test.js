import test from 'node:test';
import assert from 'node:assert/strict';
import { casePhaseLabel } from './model.js';

test('a saved report takes precedence over stale Judge waiting progress', () => {
  assert.equal(casePhaseLabel({ execution_status: 'failed', stage: 'judge_wait', report_received: true }),
    'Judge completed · report received');
  assert.equal(casePhaseLabel({ execution_status: 'failed', stage: 'judge_wait',
    result: { benchmark: { report: { status: 'issue' } } } }), 'Judge completed · report received');
});

test('terminal errors cannot display an active Judge wait', () => {
  assert.equal(casePhaseLabel({ execution_status: 'blocked', stage: 'judge_wait' }), 'Judge did not complete');
  assert.equal(casePhaseLabel({ execution_status: 'waiting_judge', stage: 'judge_wait' }),
    'Judge accepted · waiting for report');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { jobProgress } from './model.js';

const job = (...statuses) => ({ generation_status: 'running', cases: statuses.map(execution_status => ({ execution_status })) });

test('completed Cases replace stale Agent generation progress', () => {
  assert.equal(jobProgress(job('completed', 'completed', 'succeeded')), 'Completed 3/3');
  assert.equal(jobProgress({ generation_status: 'running', cases: [
    { status: 'failed', result: { benchmark: { report: { status: 'issue' } } } },
  ] }), 'Completed 1/1');
});

test('Agent progress reflects a mixed retry and blocked Case set', () => {
  assert.equal(jobProgress(job('completed', 'retrying', 'retry_wait', 'blocked')),
    'Completed 1/4 · Retrying 1 · Temporary failure / retry pending 1 · Needs attention 1');
  assert.equal(jobProgress(job('completed', 'running', 'running')), 'Completed 1/3 · Running 2');
});

test('unstarted and preparing Cases remain distinct from active generation', () => {
  assert.equal(jobProgress(job('pending_generation', 'prepared', 'generating')),
    'Completed 0/3 · Pending generation 1 · Prepared 1 · Generating 1');
  assert.equal(jobProgress({ generation_status: 'running' }), 'No Cases yet');
});

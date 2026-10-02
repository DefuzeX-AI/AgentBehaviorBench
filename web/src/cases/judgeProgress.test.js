import test from 'node:test';
import assert from 'node:assert/strict';
import { judgeProgress } from './judgeProgress.js';

test('persisted host queue status distinguishes queued, submitting and accepted Judge', () => {
  const item = { execution_status: 'waiting_judge' };
  assert.equal(judgeProgress({ ...item, judge_delivery_status: 'queued' }).title, 'Judge queued');
  assert.equal(judgeProgress({ ...item, judge_delivery_status: 'submitting' }).title, 'Submitting Judge evidence');
  assert.equal(judgeProgress({ ...item, judge_delivery_status: 'judging' }).title, 'Waiting for Judge report');
  assert.equal(judgeProgress({ ...item, stage: 'judge_queue', report_received: true }), null);
  assert.equal(judgeProgress({ ...item, stage: 'judge_queue', execution_status: 'blocked' }), null);
});

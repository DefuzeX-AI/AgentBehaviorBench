import test from 'node:test';
import assert from 'node:assert/strict';
import { attemptReport } from './caseAttemptModel.js';

test('a historical Attempt without a report cannot show the latest Case verdict', () => {
  const previous = { attempt_id: 'old', result: { error: 'timeout' } };
  const current = { attempt_id: 'new', result: { benchmark: { report: { status: 'pass' } } } };
  const item = { attempts: [previous, current], result: current.result };
  assert.equal(attemptReport(item, previous), null);
  assert.equal(attemptReport(item, null), null);
  assert.deepEqual(attemptReport(item, current), { status: 'pass' });
});

test('the selected Attempt keeps its retained report when an artifact has a later verdict', () => {
  const attempt = { result: { benchmark: { report: { status: 'issue' } } } };
  assert.deepEqual(attemptReport({}, attempt, { judge: { status: 'pass' } }), { status: 'issue' });
  assert.deepEqual(attemptReport({}, attempt, null), { status: 'issue' });
});

test('artifact reports are a fallback only for an unambiguous Attempt owner', () => {
  const previous = { attempt_id: 'old', artifact_run_id: 'run' };
  const current = { attempt_id: 'new', artifact_run_id: 'run' };
  const evaluation = { judge: { status: 'pass' } };
  assert.deepEqual(attemptReport({ attempts: [previous] }, previous, evaluation), { status: 'pass' });
  assert.equal(attemptReport({ attempts: [previous, current] }, previous, evaluation), null);
  assert.equal(attemptReport({ attempts: [previous, current] }, current, evaluation), null);
  assert.equal(attemptReport({}, previous, evaluation), null);
});

test('legacy Cases without Attempt records can display their own saved report', () => {
  assert.deepEqual(attemptReport({ attempts: [], report: { status: 'issue' } }, null), { status: 'issue' });
});

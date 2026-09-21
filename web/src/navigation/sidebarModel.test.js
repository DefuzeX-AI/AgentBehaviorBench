import test from 'node:test';
import assert from 'node:assert/strict';
import { caseNavigationTitle, compactIdentity, suiteNavigationSummary } from './sidebarModel.js';

test('sidebar builds a readable Case title from the first benchmark prompt line', () => {
  const item = { case_index: 1, result: { benchmark: { steps: [{ payload: 'Create a fixture.\nIgnore this line.' }] } } };
  assert.equal(caseNavigationTitle(item), 'Case 2: Create a fixture.');
});

test('sidebar uses a stable title while Case generation is pending', () => {
  assert.equal(caseNavigationTitle({ case_index: 0 }), 'Case 1');
});

test('sidebar summarizes execution, Judge coverage, and total pass rate independently', () => {
  const cases = [
    { execution_status: 'completed', report_received: true, judge_status: 'pass' },
    { execution_status: 'running', report_received: false },
    { execution_status: 'completed', report_received: false, judge_status: 'pass' },
  ];
  assert.deepEqual(suiteNavigationSummary(cases), { total: 3, complete: 2, judged: 1, percentage: 67 });
});

test('sidebar compacts long identities and supports prefix-only labels', () => {
  assert.equal(compactIdentity('suite_1234567890abcdef', 9, 4), 'suite_123…cdef');
  assert.equal(compactIdentity('case_1234567890abcdef', 9, 0), 'case_1234…');
});

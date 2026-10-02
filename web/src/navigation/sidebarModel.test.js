import test from 'node:test';
import assert from 'node:assert/strict';
import { caseNavigationTitle, compactIdentity, suiteNavigationSummary } from './sidebarModel.js';
import { normalizeCases } from '../suite/model.js';

test('sidebar builds a readable Case title from the first benchmark prompt line', () => {
  const item = { case_index: 1, result: { benchmark: { steps: [{ payload: 'Create a fixture.\nIgnore this line.' }] } } };
  assert.equal(caseNavigationTitle(item), 'Case 2: Create a fixture.');
});

test('sidebar uses a stable title while Case generation is pending', () => {
  assert.equal(caseNavigationTitle({ case_index: 0 }), 'Case 1');
});

test('sidebar summarizes execution completion and Judge coverage independently', () => {
  const cases = [
    { execution_status: 'completed', report_received: true, judge_status: 'pass' },
    { execution_status: 'running', report_received: false },
    { execution_status: 'completed', report_received: false },
  ];
  assert.deepEqual(suiteNavigationSummary(cases), { total: 3, complete: 2, judged: 1, percentage: 67 });
});

test('a completed single Case shows 100% regardless of its Judge verdict', () => {
  for (const verdict of ['pass', 'issue', 'insufficient_evidence', null]) {
    const cases = normalizeCases({ suite_id: 'suite-one', jobs: [{ agent_id: 'agent-one', cases: [{
      case_index: 0, execution_status: 'completed', report_received: Boolean(verdict), judge_status: verdict,
    }] }] });
    assert.deepEqual(suiteNavigationSummary(cases), {
      total: 1, complete: 1, judged: verdict ? 1 : 0, percentage: 100,
    }, `Judge verdict: ${verdict}`);
  }
});

test('sidebar completion follows updated execution state rather than Judge pass results', () => {
  const summary = execution_status => suiteNavigationSummary(normalizeCases({
    suite_id: 'suite-one', jobs: [{ agent_id: 'agent-one', cases: [{
      case_index: 0, execution_status, report_received: false, judge_status: 'pass',
    }] }],
  }));
  assert.equal(summary('running').percentage, 0);
  assert.equal(summary('succeeded').percentage, 100);
  assert.deepEqual(suiteNavigationSummary([]), { total: 0, complete: 0, judged: 0, percentage: 0 });
});

test('sidebar compacts long identities and supports prefix-only labels', () => {
  assert.equal(compactIdentity('suite_1234567890abcdef', 9, 4), 'suite_123…cdef');
  assert.equal(compactIdentity('case_1234567890abcdef', 9, 0), 'case_1234…');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { filterCases, latestTimestamp, sortCases } from './tableModel.js';

const cases = [
  { key: 'b', agent_id: 'beta', case_index: 1, case_id: 'case-red', execution_status: 'failed', judge_status: 'issue', retry_count: 1,
    attempts: [{ attempt_id: '1', finished_at: '2026-01-02T00:00:00Z' }, { attempt_id: '2' }] },
  { key: 'a', agent_id: 'alpha', case_index: 0, case_id: 'case-green', execution_status: 'completed', judge_status: 'pass', retry_count: 0,
    attempts: [{ attempt_id: '1', finished_at: '2026-01-01T00:00:00Z' }] },
  { key: 'c', agent_id: 'alpha', case_index: 2, execution_status: 'queued', judge_status: null, retry_count: 0, attempts: [] },
];

const emptyFilters = { query: '', agents: [], statuses: [], judges: [], attention: false, retried: false };

test('Case filters compose query, facets, attention, and retry state', () => {
  assert.deepEqual(filterCases(cases, { ...emptyFilters, query: 'green' }).map(item => item.key), ['a']);
  assert.deepEqual(filterCases(cases, { ...emptyFilters, agents: ['alpha'], judges: ['not_received'] }).map(item => item.key), ['c']);
  assert.deepEqual(filterCases(cases, { ...emptyFilters, attention: true, retried: true }).map(item => item.key), ['b']);
});

test('Case sorting supports stable table columns', () => {
  assert.deepEqual(sortCases(cases, 'case', 'ascend').map(item => item.key), ['a', 'c', 'b']);
  assert.deepEqual(sortCases(cases, 'attempts', 'descend').map(item => item.key), ['b', 'a', 'c']);
  assert.deepEqual(sortCases(cases, 'updated', 'descend').map(item => item.key), ['b', 'a', 'c']);
  assert.equal(latestTimestamp(cases[0]), Date.parse('2026-01-02T00:00:00Z'));
});

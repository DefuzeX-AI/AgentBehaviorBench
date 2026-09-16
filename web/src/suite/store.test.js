import test from 'node:test';
import assert from 'node:assert/strict';
import { actions, createSuiteStore } from './store.js';
import { countCases, normalizeCases, caseKey } from './model.js';

function snapshot(revision, updates = {}) {
  return { suite_id: 'suite-a', revision, jobs: [
    { agent_id: 'alpha', cases: [{ case_index: 0, status: 'failed', result: { benchmark: { report: { status: 'issue' } } } },
      { case_index: 1, execution_status: 'retry_wait', active_attempt_id: 'try-1',
        attempts: [{ attempt_id: 'try-1', artifact_run_id: 'old-run', status: 'failed' }], ...updates }] },
    { agent_id: 'beta', cases: [{ case_index: 0, status: 'queued' }] },
  ] };
}
const receive = (store, value) => store.dispatch(actions.snapshotReceived({ snapshot: value, updated: 'now' }));

test('all planned slots count once; Judge issue is separate from execution error', () => {
  const cases = normalizeCases(snapshot(1));
  assert.equal(cases.length, 3);
  assert.equal(new Set(cases.map(item => item.key)).size, 3);
  assert.equal(cases[0].execution_status, 'completed');
  assert.equal(cases[0].judge_status, 'issue');
  assert.deepEqual(countCases(cases), { completed: 1, running: 0, retry_wait: 1, attention: 0, queued: 1, reports: 1, accepted: 0 });
});

test('retry transition keeps historical attempt and several cases expanded', () => {
  const store = createSuiteStore();
  receive(store, snapshot(1));
  const cases = normalizeCases(store.getState().suite.snapshot);
  cases.slice(0, 2).forEach(item => store.dispatch(actions.caseToggled(item)));
  receive(store, snapshot(2, { execution_status: 'retrying', active_attempt_id: 'try-2', attempts: [
    { attempt_id: 'try-1', artifact_run_id: 'old-run', status: 'failed' },
    { attempt_id: 'try-2', artifact_run_id: 'new-run', status: 'running' },
  ] }));
  const state = store.getState().suite;
  assert.equal(Object.values(state.expanded).filter(Boolean).length, 2);
  assert.equal(state.selectedAttempts[cases[1].key], 'try-1');
  assert.equal(normalizeCases(state.snapshot)[1].attempts.length, 2);
  assert.equal(normalizeCases(state.snapshot).length, 3);
  store.dispatch(actions.attemptSelected({ key: cases[1].key, attempt_id: 'try-2' }));
  assert.equal(store.getState().suite.selectedAttempts[cases[1].key], 'try-2');
});

test('disconnection and out-of-order snapshots cannot erase completed results', () => {
  const store = createSuiteStore();
  receive(store, snapshot(5, { execution_status: 'completed', judge_status: 'pass' }));
  const latest = store.getState().suite.snapshot;
  store.dispatch(actions.connectionFailed('offline'));
  assert.equal(store.getState().suite.snapshot, latest);
  receive(store, snapshot(3));
  assert.equal(store.getState().suite.snapshot, latest);
  receive(store, snapshot(5));
  assert.equal(store.getState().suite.snapshot, latest);
  assert.equal(store.getState().suite.error, '');
  receive(store, snapshot(6, { execution_status: 'blocked' }));
  assert.equal(normalizeCases(store.getState().suite.snapshot)[1].execution_status, 'blocked');
});

test('Suite identity cannot change from a polling response', () => {
  const store = createSuiteStore();
  receive(store, snapshot(1));
  receive(store, { ...snapshot(2), suite_id: 'suite-other' });
  assert.equal(store.getState().suite.snapshot.suite_id, 'suite-a');
  assert.match(store.getState().suite.error, /identity/);
  assert.notEqual(caseKey('suite-a', 'alpha', 0), caseKey('suite-other', 'alpha', 0));
});

test('host rejected report remains visible without claiming execution completed', () => {
  const value = snapshot(1);
  value.jobs[0].cases[0].host_accepted = false;
  const item = normalizeCases(value)[0];
  assert.equal(item.execution_status, 'failed');
  assert.equal(item.report_received, true);
  assert.equal(countCases([item]).accepted, 0);
});

test('legacy artifact identity is explicit; no lookup by Agent and case position', () => {
  const value = snapshot(1);
  value.jobs[1].cases[0].artifact_run_id = 'bound-artifact';
  const item = normalizeCases(value)[2];
  assert.equal(item.attempts[0].artifact_run_id, 'bound-artifact');
  assert.equal(normalizeCases(value)[0].attempts.length, 0);
});

test('accepted command is reconciled by the coordinator snapshot', () => {
  const store = createSuiteStore();
  store.dispatch(actions.commandStarted({ command_id: 'one' }));
  store.dispatch(actions.commandFinished({ command_id: 'other', status: 'completed' }));
  assert.equal(store.getState().suite.command.status, 'sending');
  receive(store, { ...snapshot(1), commands: [{ command_id: 'one', status: 'completed' }] });
  assert.equal(store.getState().suite.command.status, 'completed');
});

test('viewer capabilities refresh without advancing the Case revision', () => {
  const store = createSuiteStore();
  receive(store, { ...snapshot(1), capabilities: { can_control: true, control_token: 'old-token' } });
  receive(store, { ...snapshot(1), capabilities: { can_control: true, control_token: 'new-token' } });
  assert.equal(store.getState().suite.snapshot.capabilities.control_token, 'new-token');
  assert.equal(store.getState().suite.snapshot.revision, 1);
});

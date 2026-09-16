import test from 'node:test';
import assert from 'node:assert/strict';
import { actions, createSuiteStore } from './store.js';
import { controlCapability, resendSuiteCommand, sendSuiteCommand } from './commands.js';

const origin = 'http://localhost:5173';
function controlledStore() {
  const store = createSuiteStore();
  store.dispatch(actions.snapshotReceived({ snapshot: { suite_id: 's', revision: 7, jobs: [],
    capabilities: { can_control: true, control_url: '/api/suites/s/control', control_token: 'test-only' } } }));
  return store;
}

test('duplicate clicks send one command, including exact case index zero', async () => {
  const store = controlledStore();
  const requests = [];
  let respond;
  const dependencies = { origin, uuid: () => 'cmd-one', fetch: async (url, options) => {
    requests.push({ url, options });
    await new Promise(resolve => { respond = resolve; });
    return { ok: true, json: async () => ({ status: 'accepted' }) };
  } };
  const first = store.dispatch(sendSuiteCommand('retry', { agent_id: 'alpha', case_index: 0 }, dependencies));
  await store.dispatch(sendSuiteCommand('retry', { agent_id: 'alpha', case_index: 0 }, dependencies));
  assert.equal(requests.length, 1);
  assert.deepEqual(JSON.parse(requests[0].options.body), { command_id: 'cmd-one', action: 'retry', agent_id: 'alpha', case_index: 0, expected_revision: 7 });
  assert.equal(requests[0].options.headers['X-ABB-Control-Token'], 'test-only');
  respond(); await first;
  assert.equal(store.getState().suite.command.status, 'accepted');
});

test('uncertain response keeps command identity for an idempotent resend', async () => {
  const store = controlledStore();
  await store.dispatch(sendSuiteCommand('resume', null, { origin, uuid: () => 'same-id', fetch: async () => { throw new Error('disconnected'); } }));
  assert.equal(store.getState().suite.command.status, 'uncertain');
  let resent;
  await store.dispatch(resendSuiteCommand({ origin, fetch: async (_, options) => {
    resent = JSON.parse(options.body);
    return { ok: true, json: async () => ({ status: 'completed' }) };
  } }));
  assert.equal(resent.command_id, 'same-id');
  assert.equal(resent.action, 'resume');
  assert.equal(store.getState().suite.command.status, 'completed');
});

test('read-only and remote capabilities cannot send commands', async () => {
  assert.equal(controlCapability({}, origin), null);
  assert.equal(controlCapability({ capabilities: { can_control: true, control_token: 'secret', control_url: 'https://example.com/receive' } }, origin), null);
  const store = createSuiteStore();
  let called = false;
  await store.dispatch(sendSuiteCommand('resume', null, { origin, fetch: () => { called = true; } }));
  assert.equal(called, false);
});

test('revision conflict is shown as rejection without replacing result state', async () => {
  const store = controlledStore();
  await store.dispatch(sendSuiteCommand('resume', null, { origin, uuid: () => 'conflict', fetch: async () => ({ ok: false, status: 409, json: async () => ({ error: 'Refresh before retrying.' }) }) }));
  assert.equal(store.getState().suite.command.status, 'rejected');
  assert.equal(store.getState().suite.snapshot.revision, 7);
});

test('server errors retain the command identity because execution might have started', async () => {
  const store = controlledStore();
  await store.dispatch(sendSuiteCommand('resume', null, { origin, uuid: () => 'server-error', fetch: async () => ({ ok: false, status: 500, json: async () => ({ error: 'Reply interrupted.' }) }) }));
  assert.equal(store.getState().suite.command.status, 'uncertain');
  assert.equal(store.getState().suite.command.command_id, 'server-error');
});

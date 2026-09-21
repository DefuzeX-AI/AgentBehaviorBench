import test from 'node:test';
import assert from 'node:assert/strict';
import { suiteActivity } from './activityModel.js';
test('shows all concurrent cases and does not infer an executing case during batch generation', () => {
  const cases = [{ agent_id: 'a', case_index: 0, execution_status: 'running' }, { agent_id: 'a', case_index: 1, execution_status: 'judging' }, { agent_id: 'b', execution_status: 'pending_generation' }];
  const jobs = [{ agent_id: 'a', status: 'running' }, { agent_id: 'b', status: 'running', generation_status: 'running' }, { agent_id: 'c', status: 'failed' }];
  const result = suiteActivity(cases, jobs);
  assert.equal(result.active.length, 2);
  assert.deepEqual(result.preparing.map(job => job.agent_id), ['b']);
});
test('finished cases are not shown as active', () => {
  assert.deepEqual(suiteActivity([{ agent_id: 'a', execution_status: 'completed' }], [{ agent_id: 'a', status: 'succeeded' }]), {active: [], preparing: []});
});

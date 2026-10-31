import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { interactionPage } from './interactions.js';

test('Vite serves the Python interaction contract with pagination and rejects escapes', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-interactions-'));
  try {
    await mkdir(path.join(root, 'run'));
    await writeFile(path.join(root, 'run/network.jsonl'), Array.from({ length: 11 }, (_, i) => JSON.stringify({
      event: 'llm_request', timestamp: `2026-09-10T07:00:${String(i).padStart(2, '0')}Z`,
      data: { call_id: `call-${i}`, model: 'arbitrary-model', payload: { messages: [] } },
    })).join('\n'));
    const page = await interactionPage(root, 'run', { page: 2, page_size: 10 });
    assert.equal(page.total, 11); assert.equal(page.items.length, 1);
    const detail = await interactionPage(root, 'run', { id: page.items[0].id });
    assert.equal(detail.request.call_id, 'call-10');
    await assert.rejects(interactionPage(root, '../run', {}));
    await symlink(tmpdir(), path.join(root, 'escape'));
    await assert.rejects(interactionPage(root, 'escape', {}));
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('Vite trajectory bridge serves the derived step sequence of an attempt', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-trajectory-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const step = path.join(root, 'run/steps/0001');
  await mkdir(step, { recursive: true });
  await writeFile(path.join(root, 'run/run.json'), JSON.stringify({ run_id: 'run', agent_id: 'alpha', case_id: 'c', status: 'succeeded' }));
  await writeFile(path.join(step, 'input.json'), JSON.stringify({ input_id: 'step-1', case_id: 'c', payload: 'hi' }));
  await writeFile(path.join(step, 'request.json'), JSON.stringify({ agent_id: 'alpha', framework: 'langgraph', input: 'hi' }));
  await writeFile(path.join(step, 'result.json'), JSON.stringify({ status: 'succeeded', output: 'hello' }));
  const trajectory = await interactionPage(root, 'run', {}, undefined, 'agentbench.trajectory');
  assert.equal(trajectory.schema, 'abb.agent-trajectory.v1');
  assert.equal(trajectory.derived_on_read, true);
  assert.deepEqual(trajectory.steps, []);
  assert.equal(trajectory.inputs[0].result.output, 'hello');
  await writeFile(path.join(root, 'run/run.json'), JSON.stringify({ run_id: 'run', agent_id: 'alpha', case_id: 'c', status: 'running' }));
  const pending = await interactionPage(root, 'run', {}, undefined, 'agentbench.trajectory');
  assert.equal(pending.status, 'pending');
  assert.equal(pending.steps, undefined);
});

test('Vite timing bridge reads saved measurements again after reopening', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-timeline-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'run'));
  const pathToJournal = path.join(root, 'run/timing.jsonl');
  const record = duration => JSON.stringify({ event: 'operation', timestamp: '2026-01-01T00:00:00Z', data: {
    id: 'stage', name: 'Evaluation', kind: 'total', source: 'host', status: 'succeeded',
    start_ms: 1000, end_ms: 1000 + duration, duration_ms: duration,
  } });
  await writeFile(pathToJournal, `${record(200)}\n`);
  const read = () => interactionPage(root, 'run', {}, undefined, 'agentbench.observe.timeline');
  assert.equal((await read()).operations[0].duration_ms, 200);
  await writeFile(pathToJournal, `${record(200)}\n${record(500)}\n`);
  const reopened = await read();
  assert.equal(reopened.schema, 'abb.timeline.v1');
  assert.equal(reopened.operations.length, 1);
  assert.equal(reopened.operations[0].duration_ms, 500);
});

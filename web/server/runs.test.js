import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { listRuns, readRun, runsPlugin } from './runs.js';

async function fixture(t) {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-runs-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'run1/invocation-a/output'), { recursive: true });
  await writeFile(path.join(root, 'run1/run.json'), JSON.stringify({ agent_id: 'research-agent', input: { query: '中文任务' }, status: 'succeeded', output: 'not in list' }));
  return root;
}

test('list metadata and load both trace sources without exposing report', async t => {
  const root = await fixture(t);
  const runs = await listRuns(root);
  assert.equal(runs[0].agent, 'research-agent');
  assert.equal(runs[0].id, 'run1');
  assert.equal(runs[0].output, undefined);
  await writeFile(path.join(root, 'run1/network.jsonl'), '{"event":"llm_request"}\n');
  await writeFile(path.join(root, 'run1/invocation-a/output/framework.jsonl'), '{"event":"span_start"}\n');
  assert.equal((await readRun(root, 'run1')).files.length, 2);
});

test('each run is independent of agent-specific input shape', async t => {
  const root = await fixture(t);
  const inputs = [{ company: 'not a run title' }, { prompt: 'fix code' }, ['message'], 'plain text', null];
  for (const [index, input] of inputs.entries()) {
    const id = `generic-${index}`;
    await mkdir(path.join(root, id));
    await writeFile(path.join(root, id, 'run.json'), JSON.stringify({
      run_id: id, agent_id: 'coding-agent', input, status: 'succeeded',
    }));
  }
  const runs = (await listRuns(root)).filter(run => run.agent === 'coding-agent');
  assert.equal(runs.length, inputs.length);
  assert.equal(new Set(runs.map(run => run.id)).size, inputs.length);
  for (const run of runs) {
    assert.deepEqual(Object.keys(run).sort(), ['agent', 'id', 'status', 'updated']);
  }
});

test('missing traces, malformed metadata and absent root are explicit', async t => {
  const root = await fixture(t);
  assert.equal((await readRun(root, 'run1')).warnings.length, 1);
  await writeFile(path.join(root, 'run1/run.json'), '{');
  assert.equal((await listRuns(root))[0].status, 'unavailable');
  assert.deepEqual(await listRuns(path.join(root, 'absent')), []);
});

test('reject traversal, external symlinks and oversized trace', async t => {
  const root = await fixture(t);
  await assert.rejects(readRun(root, '../outside'));
  await symlink(path.join(root, 'run1/run.json'), path.join(root, 'run1/network.jsonl'));
  // A link outside the selected run is never returned.
  await writeFile(path.join(root, 'secret'), 'secret');
  await symlink(path.join(root, 'secret'), path.join(root, 'run1/invocation-a/output/framework.jsonl'));
  let result = await readRun(root, 'run1');
  assert.equal(result.files.length, 1);
  assert.ok(result.warnings.length);
  await rm(path.join(root, 'run1/network.jsonl'));
  await writeFile(path.join(root, 'run1/network.jsonl'), 'x'.repeat(20 * 1024 * 1024 + 1));
  result = await readRun(root, 'run1');
  assert.equal(result.files.length, 0);
});

test('API denies cross-origin reads and writes, lists same-origin runs', async t => {
  const root = await fixture(t);
  let middleware;
  runsPlugin(root).configureServer({ middlewares: { use(fn) { middleware = fn; } } });
  async function call(method, headers) {
    const response = { setHeader() {}, end(body) { this.body = JSON.parse(body); } };
    await middleware({ url: '/api/observe/runs', method, headers }, response, () => assert.fail('unexpected fallthrough'));
    return response;
  }
  assert.equal((await call('GET', { host: 'evil.example' })).statusCode, 403);
  assert.equal((await call('GET', { host: 'localhost:5173', origin: 'https://evil.example' })).statusCode, 403);
  assert.equal((await call('POST', { host: 'localhost:5173' })).statusCode, 405);
  assert.equal((await call('GET', { host: 'localhost:5173' })).body.runs.length, 1);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, mkdir, writeFile, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { evaluation } from './evaluation.js';
import { runsPlugin } from './runs.js';

const project = fileURLToPath(new URL('../../', import.meta.url));
const venv = path.join(project, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const python = process.env.ABB_PYTHON || (existsSync(venv) ? venv : 'python3');

async function fixture(t, metadata = { status: 'succeeded' }) {
  const temporary = await mkdtemp(path.join(tmpdir(), 'abb-evaluation-test-'));
  t.after(() => rm(temporary, { recursive: true, force: true }));
  const root = path.join(temporary, 'runs');
  const run = path.join(root, 'run');
  await mkdir(run, { recursive: true });
  await writeJson(path.join(run, 'run.json'), metadata);
  return { root, run, temporary };
}

async function writeJson(file, value) {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, JSON.stringify(value));
}

async function pythonEvaluation(run) {
  const { stdout } = await promisify(execFile)(python, ['-c',
    'import json, sys; from pathlib import Path; from agentbench.observe.view_api import RunViewAPI; print(json.dumps(RunViewAPI(Path(sys.argv[1])).evaluation()))',
    run], { cwd: project });
  return JSON.parse(stdout);
}

async function request(root, run = 'run', configure = 'configureServer') {
  let middleware;
  runsPlugin(root)[configure]({ middlewares: { use(fn) { middleware = fn; } } });
  const response = { setHeader() {}, end(body) { this.body = JSON.parse(body); } };
  await middleware({ url: `/api/observe/runs/${run}/evaluation`, method: 'GET',
    headers: { host: 'localhost:5173' } }, response, () => assert.fail('unexpected fallthrough'));
  return response;
}

test('evaluation without an artifact directory matches Python, including execution status', async t => {
  for (const metadata of [
    { status: 'succeeded', evaluation_result: { verdict: 'pass' } },
    { status: 'failed' },
    {},
  ]) {
    const { root, run } = await fixture(t, metadata);
    const expected = await pythonEvaluation(run);
    assert.deepEqual(expected, { public_result: metadata.evaluation_result || {},
      execution_status: metadata.status ?? null, manifest: null, process: null,
      case: null, judge: null, error: null, inputs: [] });
    assert.deepEqual(await evaluation(root, 'run'), expected);
  }
});

test('Vite dev and preview serve a run with no evaluation directory as HTTP 200', async t => {
  const { root, run } = await fixture(t, { status: 'failed', evaluation_result: { error: 'execution failed' } });
  const expected = await pythonEvaluation(run);
  for (const configure of ['configureServer', 'configurePreviewServer']) {
    const response = await request(root, 'run', configure);
    assert.equal(response.statusCode, 200);
    assert.deepEqual(response.body, expected);
  }
});

test('existing evaluation artifacts and ordered inputs keep matching Python', async t => {
  const { root, run } = await fixture(t, { status: 'succeeded', evaluation_result: { verdict: 'pass' } });
  const directory = path.join(run, 'evaluation');
  const artifacts = {
    'manifest.json': { sdk: 'test' }, 'process.json': { status: 'complete' },
    'case.json': { case_id: 'case-a' }, 'judge/report.json': { verdict: 'pass' },
    'error.json': { stage: 'judge', message: 'saved diagnostic' },
    'inputs/0002/input.json': { prompt: 'second' },
    'inputs/0001/input.json': { prompt: 'first' },
    'inputs/0001/result.json': { result: 'output' },
    'inputs/0001/submission.json': { submitted: true },
    'inputs/0001/evidence.json': { evidence: 'retained' },
  };
  for (const [relative, value] of Object.entries(artifacts)) await writeJson(path.join(directory, relative), value);
  const expected = await pythonEvaluation(run);
  assert.deepEqual(expected.inputs.map(input => input.step), ['0001', '0002']);
  assert.deepEqual(await evaluation(root, 'run'), expected);
  const response = await request(root);
  assert.equal(response.statusCode, 200);
  assert.deepEqual(response.body, expected);
});

test('a nonexistent run still fails and returns HTTP 404', async t => {
  const { root } = await fixture(t);
  await assert.rejects(evaluation(root, 'missing'), { code: 'ENOENT' });
  assert.equal((await request(root, 'missing')).statusCode, 404);
});

test('evaluation rejects traversal and external run links even without artifacts', async t => {
  const { root, temporary } = await fixture(t);
  await assert.rejects(evaluation(root, '../outside'), /Invalid run/);
  assert.equal((await request(root, '..%2Foutside')).statusCode, 404);
  const outside = path.join(temporary, 'outside');
  await writeJson(path.join(outside, 'run.json'), { status: 'secret' });
  await symlink(outside, path.join(root, 'linked'), 'junction');
  await assert.rejects(evaluation(root, 'linked'));
  assert.equal((await request(root, 'linked')).statusCode, 404);
});

test('evaluation rejects external artifact and metadata links', async t => {
  for (const relative of ['evaluation', 'evaluation/inputs', 'evaluation/manifest.json', 'run.json']) {
    await t.test(relative, async t => {
      const { root, run, temporary } = await fixture(t);
      const outside = path.join(temporary, 'outside');
      await writeJson(path.join(outside, 'manifest.json'), { secret: true });
      const target = path.join(run, relative);
      await mkdir(path.dirname(target), { recursive: true });
      if (relative === 'run.json') await rm(target);
      const directoryLink = !relative.endsWith('.json');
      await symlink(directoryLink ? outside : path.join(outside, 'manifest.json'), target,
        directoryLink ? 'junction' : 'file');
      await assert.rejects(evaluation(root, 'run'));
      assert.equal((await request(root)).statusCode, 404);
    });
  }
});

import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { createCompatibility } from '../resources/agents/77-blade-code/bootstrap/acp-compat.mjs';

function fixture(t) {
  const temporary = mkdtempSync(path.join(os.tmpdir(), 'abb-blade-acp-'));
  t.after(() => rmSync(temporary, { recursive: true, force: true }));
  const workspace = path.join(temporary, 'workspace');
  mkdirSync(workspace);
  return { temporary, workspace, bridge: createCompatibility(workspace) };
}

function fileError(bridge, requestedPath, code = -32603) {
  const request = JSON.stringify({ jsonrpc: '2.0', id: 42,
    method: 'fs/read_text_file', params: { path: requestedPath } });
  assert.equal(bridge.fromAgent(request), request);
  const error = { jsonrpc: '2.0', id: 42, error: { code, message: 'Internal error', data: { detail: 'preserved' } } };
  return { original: JSON.stringify(error), normalized: bridge.fromClient(JSON.stringify(error)) };
}

test('initialize, prompts, permissions and successful responses pass unchanged', (t) => {
  const { bridge, workspace } = fixture(t);
  for (const frame of [
    ' {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"clientCapabilities":{"fs":{"readTextFile":true,"writeTextFile":true},"terminal":true}}} ',
    '{"jsonrpc":"2.0","id":2,"method":"session/prompt","params":{"prompt":[{"type":"text","text":"中文 task"}]}}',
    '{"jsonrpc":"2.0","id":3,"method":"session/request_permission","params":{"options":[{"kind":"allow_once"}]}}',
    '{"jsonrpc":"2.0","id":3,"result":{"outcome":{"outcome":"selected","optionId":"allow_once"}}}',
    '{"jsonrpc":"2.0","id":4,"result":{"stdout":"real output","exitCode":0}}',
    'not-json', 'null', '17',
  ]) {
    assert.equal(bridge.fromClient(frame), frame);
    assert.equal(bridge.fromAgent(frame), frame);
  }
  bridge.fromAgent(JSON.stringify({ id: 42, method: 'fs/read_text_file', params: { path: path.join(workspace, 'new.py') } }));
  const success = '{"id":42,"result":{"content":"unchanged content"}}';
  assert.equal(bridge.fromClient(success), success);
});

test('shell command runs with Bash, preserving cwd, env and request identity', (t) => {
  const { bridge, workspace } = fixture(t);
  for (const args of [undefined, []]) {
    const original = { jsonrpc: '2.0', id: 'cmd', method: 'terminal/create',
      params: { command: 'printf "native shell output" > result.txt && cat result.txt',
        args, cwd: workspace, env: [{ name: 'EXAMPLE', value: 'kept' }], outputByteLimit: 4096 } };
    const output = JSON.parse(bridge.fromAgent(JSON.stringify(original)));
    assert.deepEqual(output, { ...original, params: { ...original.params,
      command: '/bin/bash', args: ['-c', original.params.command] } });
    const actual = spawnSync(output.params.command, output.params.args, { cwd: workspace, encoding: 'utf8' });
    assert.equal(actual.status, 0);
    assert.equal(actual.stdout, 'native shell output');
  }
});

test('separate command arguments are not interpreted a second time', (t) => {
  const { bridge } = fixture(t);
  const frame = '{"id":7,"method":"terminal/create","params":{"command":"python","args":["-c","print(1)"]}}';
  assert.equal(bridge.fromAgent(frame), frame);
});

test('real missing file in workspace gets ACP resource-not-found code', (t) => {
  const { bridge, workspace } = fixture(t);
  for (const requestedPath of [path.join(workspace, 'absent.py'), path.join(workspace, 'new/subdir/file.py')]) {
    const result = fileError(bridge, requestedPath);
    assert.deepEqual(JSON.parse(result.normalized).error,
      { code: -32002, message: 'File not found', data: { detail: 'preserved' } });
  }
});

test('existing files, outside files and other error codes are not rewritten', (t) => {
  const { bridge, workspace, temporary } = fixture(t);
  writeFileSync(path.join(workspace, 'exists.txt'), 'actual content');
  for (const requestedPath of [path.join(workspace, 'exists.txt'), path.join(temporary, 'outside.txt'), '../outside.txt', 'relative.txt']) {
    const result = fileError(bridge, requestedPath);
    assert.equal(result.normalized, result.original);
  }
  const other = fileError(bridge, path.join(workspace, 'missing.txt'), -32000);
  assert.equal(other.normalized, other.original);
  // A response for a consumed or unknown ID must never be inferred again.
  const late = '{"id":42,"error":{"code":-32603,"message":"Internal error"}}';
  assert.equal(bridge.fromClient(late), late);
});

test('symlink escape cannot authorize missing-file error normalization', (t) => {
  const { bridge, workspace, temporary } = fixture(t);
  const outside = path.join(temporary, 'outside');
  mkdirSync(outside);
  symlinkSync(outside, path.join(workspace, 'escape'), 'dir');
  const escaped = fileError(bridge, path.join(workspace, 'escape', 'missing.txt'));
  assert.equal(escaped.normalized, escaped.original);
  symlinkSync(path.join(temporary, 'missing-outside'), path.join(workspace, 'broken'), 'dir');
  const broken = fileError(bridge, path.join(workspace, 'broken', 'missing.txt'));
  assert.equal(broken.normalized, broken.original);
  mkdirSync(path.join(workspace, 'inside'));
  symlinkSync(path.join(workspace, 'inside'), path.join(workspace, 'safe'), 'dir');
  const safe = fileError(bridge, path.join(workspace, 'safe', 'missing.txt'));
  assert.equal(JSON.parse(safe.normalized).error.code, -32002);
});

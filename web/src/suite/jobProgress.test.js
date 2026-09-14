import test from 'node:test';
import assert from 'node:assert/strict';
import { jobProgress } from './model.js';

const job = (...statuses) => ({ generation_status: 'running', cases: statuses.map(execution_status => ({ execution_status })) });

test('completed Cases replace stale Agent generation progress', () => {
  assert.equal(jobProgress(job('completed', 'completed', 'succeeded')), '已完成 3/3');
  assert.equal(jobProgress({ generation_status: 'running', cases: [
    { status: 'failed', result: { benchmark: { report: { status: 'issue' } } } },
  ] }), '已完成 1/1');
});

test('Agent progress reflects a mixed retry and blocked Case set', () => {
  assert.equal(jobProgress(job('completed', 'retrying', 'retry_wait', 'blocked')),
    '已完成 1/4 · 正在重试 1 · 临时失败 / 等待重试 1 · 需要处理 1');
  assert.equal(jobProgress(job('completed', 'running', 'running')), '已完成 1/3 · 执行中 2');
});

test('unstarted and preparing Cases remain distinct from active generation', () => {
  assert.equal(jobProgress(job('pending_generation', 'prepared', 'generating')),
    '已完成 0/3 · 待生成 1 · 已准备 1 · 生成中 1');
  assert.equal(jobProgress({ generation_status: 'running' }), '尚无 Case');
});

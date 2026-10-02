import test from 'node:test';
import assert from 'node:assert/strict';
import { makeTimeline, unionDuration } from './timelineModel.js';

const op = (id, start, end, kind, parent_id = null) => ({ id, name: id, parent_id, kind, source: 'host',
  start_ms: start, end_ms: end, duration_ms: end - start, status: 'succeeded', observed_at_ms: end });

test('overlapping calls and nested spans never inflate total or self time', () => {
  const data = { operations: [op('total', 0, 100, 'total'), op('a', 10, 60, 'agent', 'total'), op('b', 30, 90, 'agent', 'total')] };
  const model = makeTimeline(data);
  assert.equal(model.total_ms, 100);
  assert.equal(model.agent_ms, 80);
  assert.equal(model.rows[0].self_ms, 20);
  assert.equal(unionDuration([[0, 10], [5, 12], [3, 7]]), 12);
});

test('reload does not restart clocks, terminal and stale open spans are unconfirmed', () => {
  const root = { ...op('root', 1000, 3000, 'total'), status: 'running' };
  const active = { operations: [root], observed_at_ms: 4000 };
  assert.equal(makeTimeline(active).rows[0].status, 'running');
  const stale = makeTimeline({ ...active, observed_at_ms: 100000 });
  assert.equal(stale.rows[0].status, 'unconfirmed');
  assert.equal(stale.total_ms, 2000);
  const terminal = makeTimeline({ ...active, metadata: { status: 'failed' } });
  assert.equal(terminal.rows[0].status, 'unconfirmed');
  assert.deepEqual(makeTimeline(active), makeTimeline(JSON.parse(JSON.stringify(active))));
});

test('old traces remain visible without fabricated lifecycle totals', () => {
  const data = { spans: [{ trace_id: 't', span_id: 's', name: 'model', start_time_unix_nano: '1000000000', end_time_unix_nano: '2000000000' }] };
  const model = makeTimeline(data);
  assert.equal(model.rows[0].duration_ms, 1000);
  assert.equal(model.total_ms, null);
  assert.equal(model.hasTimings, false);
});

test('framework children link to measured invocation without duplicated root envelope', () => {
  const invoke = { ...op('invoke', 1000, 4000, 'execution'), source: 'worker', attributes: { invocation_id: 'i' } };
  const model = makeTimeline({ operations: [invoke], spans: [
    { trace_id: 't', span_id: 'root', name: 'abb.execute', attributes: { 'abb.invocation_id': 'i' }, start_time_unix_nano: '1000000000', end_time_unix_nano: '5000000000' },
    { trace_id: 't', span_id: 'tool', parent_span_id: 'root', name: 'tool', attributes: { 'abb.invocation_id': 'i', 'abb.kind': 'tool' }, start_time_unix_nano: '2000000000', end_time_unix_nano: '3000000000' },
  ] });
  assert.equal(model.rows.length, 2);
  assert.equal(model.rows[1].parent_id, 'invoke');
  assert.equal(model.rows[0].self_ms, 2000);
});

test('retry and queue stages use persisted boundaries of the selected attempt', () => {
  const model = makeTimeline({}, { queued_at: '2026-01-01T00:00:09Z', started_at: '2026-01-01T00:00:10Z',
    finished_at: '2026-01-01T00:00:20Z', retry_wait_started_at: '2026-01-01T00:00:04Z', retry_released_at: '2026-01-01T00:00:09Z' });
  assert.equal(model.total_ms, 10000);
  assert.equal(model.rows.find(s => s.id === 'retry-wait').duration_ms, 5000);
  assert.equal(model.rows.find(s => s.id === 'schedule-queue').duration_ms, 1000);
});

test('historical attempts isolate recovery journals sharing the same artifact', () => {
  const original = { ...op('original', 0, 100, 'total'), attempt_id: 'a', clock_id: 'a', name: 'Evaluation' };
  const recovery = { ...op('recovery', 200, 250, 'total'), attempt_id: 'b', clock_id: 'b', name: 'Judge recovery', phase: 'recover' };
  const wait = { ...op('wait', 210, 240, 'sdk_wait', 'recovery'), clock_id: 'b' };
  const data = { operations: [original, recovery, wait] };
  assert.deepEqual(makeTimeline(data, { attempt_id: 'a' }).rows.map(s => s.id), ['original']);
  const resumed = makeTimeline(data, { attempt_id: 'b' });
  assert.deepEqual(resumed.rows.map(s => s.id), ['recovery', 'wait']);
  assert.equal(resumed.total_ms, 50);
  assert.equal(resumed.sdk_ms, 30);
  assert.equal(resumed.agent_ms, null);
  const sameAttempt = makeTimeline({ operations: [original, { ...recovery, attempt_id: 'a' }, wait] }, { attempt_id: 'a' });
  assert.deepEqual(sameAttempt.rows.map(s => s.id), ['original', 'recovery', 'wait']);
  assert.equal(sameAttempt.total_ms, 150);
});

test('missing worker timings are unknown rather than zero', () => {
  const model = makeTimeline({ operations: [op('total', 0, 100, 'total')] });
  assert.equal(model.total_ms, 100);
  assert.equal(model.agent_ms, null);
  assert.equal(model.sdk_ms, null);
});

test('runtime summary measures nested preparation once and excludes worker cleanup', () => {
  const model = makeTimeline({ operations: [op('root', 0, 100, 'total'),
    op('prepare', 0, 30, 'preparation', 'root'), op('image', 10, 25, 'preparation', 'prepare'),
    op('container', 30, 90, 'container', 'root'), op('cleanup', 90, 100, 'cleanup', 'root'),
    { ...op('worker-cleanup', 85, 90, 'cleanup'), source: 'worker' }] });
  assert.deepEqual(model.phases.map(p => p.duration_ms), [30, 60, 10]);
});

test('host Judge queue survives reload, counts elapsed time and isolates attempts', () => {
  const run = { ...op('execution', 0, 100, 'total'), attempt_id: 'a', clock_id: 'execution' };
  const queue = { ...op('queue', 100, 300, 'wait'), phase: 'judge', attempt_id: 'a', clock_id: 'host-wall' };
  const judge = { ...op('host-judge', 300, 400, 'total'), phase: 'judge', attempt_id: 'a', clock_id: 'judge' };
  const submit = { ...op('submit', 310, 390, 'judge', 'host-judge'), phase: 'judge', clock_id: 'judge' };
  const other = { ...queue, id: 'other-attempt-queue', attempt_id: 'b' };
  const data = { operations: [run, queue, judge, submit, other] };
  const model = makeTimeline(data, { attempt_id: 'a' });
  assert.equal(model.total_ms, 400);
  assert.equal(model.phases.find(p => p.label === 'Judge queue').duration_ms, 200);
  assert.equal(model.phases.find(p => p.label === 'Host Judge').duration_ms, 80);
  assert.ok(model.rows.some(s => s.id === 'queue'));
  assert.ok(!model.rows.some(s => s.id === 'other-attempt-queue'));
  assert.deepEqual(makeTimeline(JSON.parse(JSON.stringify(data)), { attempt_id: 'a' }), model);
});

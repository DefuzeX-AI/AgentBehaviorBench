import test from 'node:test';
import assert from 'node:assert/strict';
import { eventIdentity, parseTrace, sortEvents } from './trace.js';

test('parse JSONL, preserve raw Chinese content and source', () => {
  const raw = { event: 'span_start', source: 'framework', run_id: 'run', data: { input: '中文\n"原样"' } };
  const result = parseTrace(`\uFEFF${JSON.stringify(raw)}\n${JSON.stringify({ event: 'span_end' })}\n`, 'framework.jsonl');
  assert.equal(result.events.length, 2);
  assert.deepEqual(result.events[0].raw, raw);
  assert.equal(result.events[0].source, 'framework');
  assert.deepEqual(result.warnings, []);
});

test('corrupt trailing line does not discard complete events', () => {
  const result = parseTrace('{"event":"llm_request"}\n{"event":', 'network.jsonl');
  assert.equal(result.events.length, 1);
  assert.match(result.warnings[0], /行 2/);
});

test('accept pretty JSON arrays and reject non-events', () => {
  const result = parseTrace(JSON.stringify([{ event: 'start' }, null, { status: 'running' }], null, 2), 'trace.json');
  assert.equal(result.events.length, 1);
  assert.equal(result.warnings.length, 2);
  assert.equal(parseTrace('', 'empty').events.length, 0);
  assert.equal(parseTrace('null', 'null').warnings.length, 1);
});

test('merge chronological events without modifying source order', () => {
  const records = [{ timestamp: '' }, { timestamp: '2026-09-09T10:00:02Z' }, { timestamp: '2026-09-09T10:00:01Z' }];
  assert.deepEqual(sortEvents(records), [records[2], records[1], records[0]]);
  assert.equal(records[0].timestamp, '');
});

test('interleaved jobs and repeated input IDs retain Case and artifact identity', () => {
  const events = ['alpha', 'beta'].flatMap(agent => [1, 2].map(index => ({
    event: 'step_completed', agent_id: agent, job_id: `job-${agent}`,
    case_index: index - 1, case_id: `case-${index}`, artifact_run_id: `run-${agent}-${index}`,
    step: { input_id: 'input-1' },
  })));
  const parsed = parseTrace(JSON.stringify(events), 'suite.json').events;
  assert.equal(parsed.length, 4);
  assert.equal(parsed[3].runId, 'run-beta-2');
  assert.equal(eventIdentity(parsed[3]), 'beta · Job job-beta · Case 2 · case-2 · Run run-beta-2');
  assert.equal(eventIdentity(parseTrace('{"event":"start"}', 'old.json').events[0]), '');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { flattenTrajectory, ownerUnknown, parseComposer, recordSources, stepKind, stepSummary, trajectoryStats } from './chatModel.js';

test('composer sends text as typed and parses JSON input on request', () => {
  assert.deepEqual(parseComposer('你好', false), { value: '你好' });
  assert.equal(parseComposer('   ', false).error, 'Enter a message');
  assert.deepEqual(parseComposer('{"message": "hi"}', true), { value: { message: 'hi' } });
  assert.match(parseComposer('{oops', true).error, /JSON/);
});

test('steps are classified by source and tool use', () => {
  assert.equal(stepKind({ source: 'user' }), 'user');
  assert.equal(stepKind({ source: 'system' }), 'system');
  assert.equal(stepKind({ source: 'agent', message: '', tool_calls: [{ function_name: 'read' }] }), 'tool');
  assert.equal(stepKind({ source: 'agent', message: '', observation: { results: [{}] } }), 'tool');
  assert.equal(stepKind({ source: 'agent', message: 'done' }), 'assistant');
});

test('subagent steps follow the root with their depth, and stats count them', () => {
  const document = {
    trajectory_id: 'root', agent: { name: 'main' }, extra: { abb: { issues: [{ code: 'x' }] } },
    steps: [{ step_id: 1, source: 'user' }, { step_id: 2, source: 'agent', llm_call_count: 1 }],
    subagent_trajectories: [{ trajectory_id: 'child', agent: { name: 'helper' }, steps: [{ step_id: 1, source: 'agent', llm_call_count: 1 }] }],
  };
  assert.deepEqual(flattenTrajectory(document).map(row => [row.trajectoryId, row.depth, row.step.step_id]),
    [['root', 0, 1], ['root', 0, 2], ['child', 1, 1]]);
  const stats = trajectoryStats(document);
  assert.equal(stats.modelCalls, 2);
  assert.equal(stats.subagents, 1);
  assert.equal(stats.issues.length, 1);
});

test('a step and a tool call name the records that hold them', () => {
  const step = { source: 'agent', extra: { abb: { sources: ['network', 'trace'], owner: 'unknown' } },
    tool_calls: [{ function_name: 'exec', extra: { abb: { sources: ['acp'] } } }, { function_name: 'read' }] };
  assert.deepEqual(recordSources(step), ['network', 'trace']);
  assert.deepEqual(step.tool_calls.map(recordSources), [['acp'], []]);
  assert.equal(ownerUnknown(step), true);
  // A trajectory of another step source carries neither annotation.
  assert.deepEqual(recordSources({ source: 'agent', extra: { abb: {} } }), []);
  assert.equal(ownerUnknown({ source: 'agent' }), false);
});

test('a mark summary names the step briefly', () => {
  assert.deepEqual(stepSummary({ step_id: 3, source: 'agent', message: 'a\n\nb' }), { step_id: 3, source: 'agent', summary: 'a b' });
  assert.equal(stepSummary({ step_id: 4, source: 'agent', message: '', tool_calls: [{ function_name: 'exec' }] }).summary, 'exec');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { clarificationChoices, delegatedReplies, flattenTrajectory, ownerUnknown, parseComposer, recordSources, stepKind, stepSummary, trajectoryStats } from './chatModel.js';

test('late subagent text follows the delegation back to its original mailbox turn', () => {
  const user = n => ({ source: 'user', extra: { abb: { evidence: [{ file: 'steps/000' + n + '/input.json' }] } } });
  const delegation = { source: 'agent', observation: { results: [{ subagent_trajectory_ref: [{ trajectory_id: 'child' }] }] } };
  const child = { trajectory_id: 'child', agent: { name: 'Writer' }, steps: [
    { source: 'agent', message: 'Writing…', tool_calls: [{ function_name: 'write' }] },
  ] };
  const document = { steps: [user(2), delegation, delegation, user(3)], subagent_trajectories: [child] };
  assert.equal(delegatedReplies(document).get(2).get('child').message, '');
  child.steps.push({ source: 'agent', message: '已完成。', timestamp: '2026-11-28T00:11:47Z' });
  document.subagent_trajectories.push({ ...child, trajectory_id: 'unlinked' });
  const replies = delegatedReplies(document);
  assert.deepEqual([...replies.keys()], [2]);
  assert.deepEqual([...replies.get(2).values()], [
    { id: 'child', name: 'Writer', message: '已完成。', timestamp: '2026-11-28T00:11:47Z' },
  ]);
});

test('clarification buttons use the structured choice call from their own turn', () => {
  const user = n => ({ source: 'user', extra: { abb: { evidence: [{ file: 'steps/000' + n + '/input.json' }] } } });
  const args = { question: 'Which format?', options: ['PDF', 'Text', 'Slides', 'HTML'] };
  const ask = { source: 'agent', llm_call_count: 1, tool_calls: [{ function_name: 'ask_clarification', arguments: args }] };
  const result = { source: 'agent', message: '1. PDF  2. Text' };
  const steps = [user(1), ask, result, user(2), result];
  assert.deepEqual([...clarificationChoices({ steps })], [[1, { ...args, context: '' }]]);
  assert.equal(clarificationChoices({ steps: [user(1), ask, { ...result, llm_call_count: 1 }] }).size, 0);
  assert.equal(clarificationChoices({ steps: [ask] }).size, 0);
});

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

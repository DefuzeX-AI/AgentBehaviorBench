import test from 'node:test';
import assert from 'node:assert/strict';
import { coverageNotes, inputSections, provenanceNote, shouldPoll, stepTitle, stepTone } from './trajectoryModel.js';

const model = (extra = {}) => ({ step_id: 1, input_ordinal: '0001', agent_name: 'alpha', kind: 'model',
  output: { text: '', tool_calls: [] }, tool_logs: [], ...extra });

test('step titles name tools first, then the answer text, then failures', () => {
  assert.equal(stepTitle(model({ tool_logs: [{ tool_name: 'ls' }, { tool_name: 'cat' }] })), 'Model → ls, cat');
  assert.equal(stepTitle(model({ output: { text: '  The file\n says hello.' } })), 'The file says hello.');
  assert.equal(stepTitle(model({ output: { text: '', wire_error: { error_code: 'transport_error' } } })), 'Model call failed: transport_error');
  assert.equal(stepTitle({ kind: 'tool_only', tool_logs: [{ tool_name: 'exec' }] }), 'Tool: exec');
});

test('step tone reports tool errors and unobserved executions without inventing success', () => {
  assert.equal(stepTone(model()), 'neutral');
  assert.equal(stepTone(model({ tool_logs: [{ execution_status: 'error' }] })), 'issue');
  assert.equal(stepTone(model({ tool_logs: [{ execution_status: 'not_observed', link: 'none' }] })), 'warning');
  assert.equal(stepTone(model({ output: { wire_error: { error_code: 'x' } }, output_source: 'framework' })), 'neutral');
  assert.equal(stepTone(model({ output: { wire_error: { error_code: 'x' } }, output_source: 'wire' })), 'issue');
});

test('steps group under their SDK input and unassigned steps are kept', () => {
  const trajectory = { inputs: [{ ordinal: '0001', input_id: 'step-1', file_changes: [{ path: 'a' }] }],
    steps: [model(), model({ step_id: 2, input_ordinal: null })] };
  const sections = inputSections(trajectory);
  assert.deepEqual(sections.map(s => [s.ordinal, s.steps.map(x => x.step_id)]), [['0001', [1]], [null, [2]]]);
  assert.equal(sections[0].fileChanges.length, 1);
});

test('coverage notes mention gaps', () => {
  const notes = coverageNotes({ coverage: { model_calls: 'wire', tool_calls: 'acp', file_changes: 'diff',
    unobserved_tool_executions: 2 } });
  assert.ok(notes.includes('model calls: wire'));
  assert.ok(notes.some(n => n.includes('2 emitted tool calls not observed')));
});

test('provenance distinguishes the saved contract from a derivation', () => {
  assert.equal(provenanceNote({ status: 'complete' }).tone, 'saved');
  assert.equal(provenanceNote({ status: 'partial', derived_on_read: true }).tone, 'derived');
});

test('the view polls while the attempt runs or the route still answers pending, then stops', () => {
  assert.equal(shouldPoll(null, true), true);
  assert.equal(shouldPoll({ status: 'pending' }, false), true, 'attempt status may lag behind the route');
  assert.equal(shouldPoll({ status: 'complete' }, false), false);
  assert.equal(shouldPoll({ status: 'failed' }, false), false);
  assert.equal(shouldPoll(null, false), false);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { selectedGeneration, resultSources } from './generationModel.js';

test('generation selects the exact Case and distinguishes imports, failures and active slots', () => {
  const cases = [{ entry: { case_index: 0, case_id: 'a' } }, { entry: { case_index: 1, case_id: 'b' } }];
  const data = { cases, metadata: {}, collection: { failures: [{ case_index: 2, code: 'quota_exhausted' }], active_case_index: 3 } };
  assert.equal(selectedGeneration(data, { case_index: 1, case_id: 'b' }).saved, cases[1]);
  assert.equal(selectedGeneration(data, { case_index: 1, case_id: 'different' }).saved, undefined);
  assert.equal(selectedGeneration(data, { case_index: 2 }).status, 'Failed');
  assert.equal(selectedGeneration(data, { case_index: 3 }).status, 'Generating');
  assert.equal(selectedGeneration(null, { case_index: 0 }).status, 'No saved Case for this slot');
  assert.equal(selectedGeneration({ ...data, metadata: { schema: 'abb.case_collection.import.v1' } }, { case_index: 0 }).status, 'Imported');
});

test('result sources only include this attempt and its registered preparation runs', () => {
  const sources = resultSources('attempt-old', ['prepare', 'prepare', null]);
  assert.deepEqual(sources.map(source => source.value), ['attempt-old', 'prepare']);
  assert.deepEqual(resultSources(null, []), []);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectContent } from './contentFormat.js';

test('detects serialized JSON and preserves the original evidence', () => {
  const raw = '  {"response":"Hello\\n\\n**world**", "messages": []}  ';
  const result = inspectContent(raw);
  assert.equal(result.json, true);
  assert.equal(result.responseKey, 'response');
  assert.equal(result.parsed.response, 'Hello\n\n**world**');
  assert.equal(result.raw, raw);
});

test('does not classify braces alone as valid JSON', () => {
  for (const raw of ['{not JSON}', '# Heading\n- list', '{"a":1} trailing text']) {
    assert.equal(inspectContent(raw).json, false);
    assert.equal(inspectContent(raw).raw, raw);
  }
});

test('supports objects, arrays, fenced JSON and falsy outputs', () => {
  assert.deepEqual(inspectContent({ x: [1, 2] }).parsed, { x: [1, 2] });
  assert.deepEqual(inspectContent('```json\n[1,2]\n```').parsed, [1, 2]);
  for (const value of [false, 0, null]) {
    assert.equal(inspectContent(value).json, true);
    assert.equal(inspectContent(value).parsed, value);
  }
  assert.equal(inspectContent('').raw, '');
});

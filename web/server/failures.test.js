import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyFailure } from './failures.js';

test('provider-specific quota evidence preserves original message', () => {
  const message = "This request exceeds your plan's set usage limit. Please upgrade your plan.";
  const result = classifyFailure('tavily.search', message, 'framework.jsonl:2', 'a');
  assert.equal(result.category, 'quota_exceeded');
  assert.equal(result.message, message);
  assert.equal(classifyFailure('other.search', message).category, 'tool_error');
});
test('429 and unknown codes are not labelled quota exhaustion', () => {
  assert.equal(classifyFailure('tavily.search', { code: '429', message: 'Too many requests' }).category, 'tool_error');
  assert.equal(classifyFailure('tavily.search', 'Unexpected failure').message, 'Unexpected failure');
  assert.equal(classifyFailure('tavily.search', null), null);
});

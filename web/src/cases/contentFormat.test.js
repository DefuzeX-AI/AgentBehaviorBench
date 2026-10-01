import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectContent, readableMessages } from './contentFormat.js';

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

test('reads nested framework messages without exposing empty metadata as prose', () => {
  const value = [[{ type: 'system', content: 'System\nmessage', additional_kwargs: {} },
    { type: 'human', content: 'Question', id: 'message-id' }]];
  const original = JSON.stringify(value);
  const messages = readableMessages(value);
  assert.deepEqual(messages.map(m => [m.role, m.content]), [['System', 'System\nmessage'], ['User', 'Question']]);
  assert.equal(JSON.stringify(value), original);
});

test('reads generation output and retains tool calls and mixed content blocks', () => {
  const tools = [{ name: 'search', args: { query: 'docs' } }];
  const blocks = [{ type: 'text', text: 'Searching' }, { type: 'image', source: { data: 'fixture' } }];
  const [message] = readableMessages({ generations: [[{ message: { type: 'ai', content: blocks, tool_calls: tools } }]], llm_output: {} });
  assert.equal(message.role, 'Assistant');
  assert.deepEqual(message.content, blocks);
  assert.deepEqual(message.tools, tools);
  assert.equal(readableMessages({ role: 'assistant', content: '', additional_kwargs: { tool_calls: tools } })[0].tools, tools);
});

test('unknown and mixed arrays keep the full JSON fallback', () => {
  for (const value of [null, [], [1, 2], [{ role: 'user', content: 'ok' }, { other: 'keep me' }], { messages: 'text' }]) {
    assert.deepEqual(readableMessages(value), []);
  }
  assert.equal(inspectContent({ answer: 'Readable answer', messages: [] }).responseKey, 'answer');
});

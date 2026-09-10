import test from 'node:test';
import assert from 'node:assert/strict';
import { requestMessages, responseMessages } from './protocols.js';

test('OpenAI stream reconstructs Unicode, interleaved choices and fragmented tool arguments', () => {
  const result = responseMessages({ events: [
    { choices: [{ index: 0, delta: { content: '你好', tool_calls: [{ index: 0, id: 'x', function: { name: 'arbitrary', arguments: '{"城市":' } }] } }] },
    { choices: [{ index: 1, delta: { content: '另一条' } }] },
    { choices: [{ index: 0, delta: { content: '世界', tool_calls: [{ index: 0, function: { arguments: '"北京"}' } }] }, finish_reason: 'tool_calls' }] },
    { choices: [], usage: { total_tokens: 12 } }, '[DONE]',
  ] });
  assert.equal(result.messages[0].content, '你好世界');
  assert.deepEqual(result.messages[0].tool_calls, [{ id: 'x', name: 'arbitrary', arguments: { 城市: '北京' } }]);
  assert.equal(result.messages[1].content, '另一条');
  assert.equal(result.usage.total_tokens, 12);
});

test('Anthropic streams and Gemini function calls are recognized by protocol fields', () => {
  const a = responseMessages({ events: [
    { type: 'content_block_start', index: 0, content_block: { type: 'tool_use', id: 'tool-a', name: 'search', input: {} } },
    { type: 'content_block_delta', index: 0, delta: { partial_json: '{"q":' } },
    { type: 'content_block_delta', index: 0, delta: { partial_json: '"任意内容"}' } },
  ] });
  assert.deepEqual(a.messages[0].tool_calls[0].arguments, { q: '任意内容' });
  const g = responseMessages({ candidates: [{ content: { parts: [{ text: '检查' }, { functionCall: { name: 'x', args: { y: 1 } } }] } }] });
  assert.equal(g.messages[0].content, '检查');
  assert.deepEqual(g.messages[0].tool_calls[0].arguments, { y: 1 });
});

test('Responses handles in-flight tools and uses completed output without duplicating deltas', () => {
  const events = [
    { type: 'response.output_item.added', output_index: 0, item: { type: 'function_call', id: 'item-a', call_id: 'call-a', name: 'lookup' } },
    { type: 'response.function_call_arguments.delta', output_index: 0, item_id: 'item-a', delta: '{"n":2}' },
  ];
  assert.deepEqual(responseMessages({ events }).messages[0].tool_calls[0].arguments, { n: 2 });
  events.push({ type: 'response.completed', response: { output: [{ type: 'message', content: [{ type: 'output_text', text: '完成' }] }], usage: { total_tokens: 3 } } });
  assert.equal(responseMessages({ events }).messages[0].content, '完成');
});

test('request roles and tool-result IDs survive; unknown JSON stays available to raw view', () => {
  assert.deepEqual(requestMessages({ messages: [{ role: 'tool', tool_call_id: 'abc', content: '{"value":1}' }] })[0],
    { id: 'request-0', role: 'tool', content: '{"value":1}', tool_calls: [], tool_call_id: 'abc' });
  assert.equal(requestMessages({ input: 'Hello' })[0].role, 'user');
  for (const value of [null, 'not json', { choices: 42 }, { candidates: {} }, { output: {} }, { events: [null, 'partial'] }]) {
    assert.equal(responseMessages(value).parsed, false);
    assert.doesNotThrow(() => requestMessages(value));
  }
  assert.deepEqual(requestMessages({ messages: { unexpected: true } }), []);
});

// Protocol adapters, not Agent-specific prompt or tool-name rules.
export function parseJson(value) {
  if (typeof value !== 'string') return value;
  try { return JSON.parse(value); } catch { return value; }
}

const array = value => Array.isArray(value) ? value : [];
const objects = value => array(value).filter(v => v && typeof v === 'object');

export function requestMessages(payload) {
  const body = parseJson(payload);
  if (!body || typeof body !== 'object') return [];
  const messages = body.messages || body.contents || (Array.isArray(body.input) ? body.input : null);
  const result = objects(messages).map((m, i) => ({
    id: `request-${i}`, role: m.role || m.type || 'unknown',
    content: m.content ?? m.parts ?? m.text ?? m,
    tool_calls: array(m.tool_calls).length ? m.tool_calls : (m.function_call ? [m.function_call] : []),
    tool_call_id: m.tool_call_id,
  }));
  if (body.system || body.systemInstruction || body.instructions)
    result.unshift({ id: 'system', role: 'system', content: body.system || body.systemInstruction || body.instructions });
  if (typeof body.input === 'string') result.push({ id: 'input', role: 'user', content: body.input });
  return result;
}

export function responseMessages(payload) {
  const body = parseJson(payload);
  if (!body || typeof body !== 'object') return { messages: [], usage: null, parsed: false };
  const choices = new Map(), blocks = new Map();
  let usage = body.usage || body.usageMetadata || null;
  const frames = Array.isArray(body.events) ? body.events : [body];
  let parsed = false;
  function choice(index = 0) {
    if (!choices.has(index)) choices.set(index, { role: 'assistant', content: '', tools: new Map() });
    return choices.get(index);
  }
  for (let frame of frames) {
    if (typeof frame === 'string') frame = parseJson(frame);
    if (!frame || typeof frame !== 'object') continue;
    usage = frame.usage || frame.usageMetadata || frame.message?.usage || usage;
    for (const c of objects(frame.choices)) {
      parsed = true;
      const target = choice(c.index || 0), m = c.delta || c.message || {};
      target.role = m.role || target.role;
      if (typeof m.content === 'string') target.content += m.content;
      else if (m.content != null) target.content = m.content;
      if (m.reasoning_content || m.reasoning) target.reasoning = (target.reasoning || '') + (m.reasoning_content || m.reasoning);
      for (const [i, tool] of objects(m.tool_calls || (m.function_call ? [{ function: m.function_call }] : [])).entries()) {
        const key = tool.index ?? i;
        const prior = target.tools.get(key) || { id: '', name: '', arguments: '' };
        prior.id = tool.id || prior.id;
        prior.name += tool.function?.name || '';
        prior.arguments += tool.function?.arguments || '';
        target.tools.set(key, prior);
      }
      target.finish_reason = c.finish_reason || target.finish_reason;
    }
    for (const [i, c] of objects(frame.candidates).entries()) {
      parsed = true;
      const target = choice(c.index ?? i);
      for (const p of objects(c.content?.parts)) {
        if (p.text) target.content += p.text;
        if (p.functionCall) target.tools.set(target.tools.size, { name: p.functionCall.name, arguments: p.functionCall.args });
      }
    }
    if (frame.type === 'content_block_start') { parsed = true; blocks.set(frame.index, { ...frame.content_block }); }
    if (frame.type === 'content_block_delta') {
      parsed = true;
      const b = blocks.get(frame.index) || {};
      if (frame.delta?.text) b.text = (b.text || '') + frame.delta.text;
      if (frame.delta?.partial_json) b.arguments = (b.arguments || '') + frame.delta.partial_json;
      blocks.set(frame.index, b);
    }
    if (frame.type === 'response.output_text.delta') { parsed = true; choice(frame.output_index || 0).content += frame.delta || ''; }
    if (frame.type === 'response.output_item.added' && frame.item?.type === 'function_call') {
      parsed = true;
      choice(frame.output_index || 0).tools.set(frame.item.id, {
        id: frame.item.call_id, name: frame.item.name, arguments: frame.item.arguments || '',
      });
    }
    if (frame.type === 'response.function_call_arguments.delta') {
      parsed = true;
      const target = choice(frame.output_index || 0), tool = target.tools.get(frame.item_id) || { arguments: '' };
      tool.arguments += frame.delta || '';
      target.tools.set(frame.item_id, tool);
    }
  }
  const content = blocks.size ? [...blocks.values()] : Array.isArray(body.content) ? body.content : null;
  if (content) {
    parsed = true;
    const target = choice();
    for (const b of objects(content)) {
      if (b.text) target.content += b.text;
      if (b.type === 'tool_use') target.tools.set(b.id, { id: b.id, name: b.name, arguments: b.arguments ?? b.input });
    }
  }
  const completed = frames.findLast(f => f?.type === 'response.completed')?.response;
  if (Array.isArray((completed || body).output)) {
    parsed = true;
    choices.clear();
    for (const [i, item] of objects((completed || body).output).entries()) {
      const target = choice(i);
      for (const block of objects(item.content)) if (block.text) target.content += block.text;
      if (item.type === 'function_call') target.tools.set(item.call_id, { id: item.call_id, name: item.name, arguments: item.arguments });
    }
    usage = completed?.usage || usage;
  }
  return { parsed, usage, messages: [...choices.values()].map((m, i) => ({ ...m, id: `response-${i}`, tools: undefined,
    tool_calls: [...m.tools.values()].map(t => ({ ...t, arguments: parseJson(t.arguments) })) })) };
}

export function inspectContent(value) {
  const raw = typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? '';
  let parsed = value;
  let json = typeof value !== 'string';
  if (!json) {
    const trimmed = value.trim();
    const fenced = trimmed.match(/^```(?:json)?\s*\n([\s\S]*?)\n```$/i);
    try {
      parsed = JSON.parse(fenced ? fenced[1] : trimmed);
      json = true;
    } catch { /* Non-JSON stays readable text/Markdown, unchanged. */ }
  }
  const responseKey = json && parsed && !Array.isArray(parsed) && typeof parsed === 'object'
    ? ['response', 'content', 'answer', 'text'].find(key => typeof parsed[key] === 'string' && parsed[key].trim()) : null;
  return { raw, json, parsed, responseKey };
}

// Recognize message envelopes, not model or Agent names. Unknown shapes keep the JSON view.
export function readableMessages(value) {
  if (!value || typeof value !== 'object') return [];
  const source = Array.isArray(value) ? value : value.messages ?? value.generations ?? [value];
  if (!Array.isArray(source)) return [];
  const entries = source.flat(Infinity);
  if (!entries.length) return [];
  const messages = entries.map(entry => {
    const message = entry?.message ?? entry;
    if (!message || typeof message !== 'object') return null;
    const role = message.role ?? message.type;
    if (typeof role !== 'string' || !Object.hasOwn(message, 'content')) return null;
    return {
      role: ({ human: 'User', user: 'User', ai: 'Assistant', assistant: 'Assistant', system: 'System', tool: 'Tool', function: 'Function' })[role] || role,
      name: message.name,
      content: message.content,
      tools: message.tool_calls?.length ? message.tool_calls : message.additional_kwargs?.tool_calls,
    };
  });
  return messages.every(Boolean) ? messages : [];
}

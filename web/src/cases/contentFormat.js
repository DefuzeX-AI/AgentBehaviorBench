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
    ? ['response', 'content'].find(key => typeof parsed[key] === 'string' && parsed[key].trim()) : null;
  return { raw, json, parsed, responseKey };
}

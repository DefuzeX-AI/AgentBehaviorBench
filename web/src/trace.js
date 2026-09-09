// No network or HTML rendering: imported trace content stays browser-local.
export function parseTrace(text, filename) {
  const events = [];
  const warnings = [];
  const content = text.replace(/^\uFEFF/, '').trim();
  if (!content) return { events, warnings };

  function append(value, location) {
    if (!value || typeof value !== 'object' || Array.isArray(value)
        || typeof value.event !== 'string' || !value.event.trim()) {
      warnings.push(`${filename} · ${location}：不是 trace 事件（缺少 event）。`);
      return;
    }
    events.push({
      id: `${filename}:${location}:${events.length}`,
      filename,
      event: value.event,
      source: typeof value.source === 'string' ? value.source : 'unknown',
      timestamp: typeof value.timestamp === 'string' ? value.timestamp : '',
      runId: typeof value.run_id === 'string' ? value.run_id : '',
      raw: value,
      search: JSON.stringify(value).toLowerCase(),
    });
  }

  try {
    const json = JSON.parse(content);
    if (Array.isArray(json)) json.forEach((value, i) => append(value, `记录 ${i + 1}`));
    else append(json, '记录 1');
  } catch {
    content.split(/\r?\n/).forEach((line, i) => {
      if (!line.trim()) return;
      try { append(JSON.parse(line), `行 ${i + 1}`); }
      catch { warnings.push(`${filename} · 行 ${i + 1}：JSON 不完整或格式错误，已跳过。`); }
    });
  }
  return { events, warnings };
}

export function sortEvents(events) {
  return [...events].sort((a, b) => {
    const first = Date.parse(a.timestamp);
    const second = Date.parse(b.timestamp);
    if (!Number.isFinite(first)) return Number.isFinite(second) ? 1 : 0;
    if (!Number.isFinite(second)) return -1;
    return first - second;
  });
}

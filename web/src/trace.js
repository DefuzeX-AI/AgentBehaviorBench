// No network or HTML rendering: imported trace content stays browser-local.
export function parseTrace(text, filename) {
  const events = [];
  const warnings = [];
  const content = text.replace(/^\uFEFF/, '').trim();
  if (!content) return { events, warnings };

  function append(value, location) {
    if (!value || typeof value !== 'object' || Array.isArray(value)
        || typeof value.event !== 'string' || !value.event.trim()) {
      warnings.push(`${filename} · ${location}: not a trace event (missing event).`);
      return;
    }
    events.push({
      id: `${filename}:${location}:${events.length}`,
      filename,
      event: value.event,
      source: typeof value.source === 'string' ? value.source : 'unknown',
      timestamp: typeof value.timestamp === 'string' ? value.timestamp : '',
      runId: typeof value.artifact_run_id === 'string' ? value.artifact_run_id : typeof value.run_id === 'string' ? value.run_id : '',
      agentId: typeof value.agent_id === 'string' ? value.agent_id : '',
      jobId: typeof value.job_id === 'string' ? value.job_id : '',
      caseIndex: value.case_index ?? null,
      caseId: typeof value.case_id === 'string' ? value.case_id : '',
      raw: value,
      search: JSON.stringify(value).toLowerCase(),
    });
  }

  try {
    const json = JSON.parse(content);
    if (Array.isArray(json)) json.forEach((value, i) => append(value, `record ${i + 1}`));
    else append(json, 'record 1');
  } catch {
    content.split(/\r?\n/).forEach((line, i) => {
      if (!line.trim()) return;
      try { append(JSON.parse(line), `line ${i + 1}`); }
      catch { warnings.push(`${filename} · line ${i + 1}: incomplete or invalid JSON; skipped.`); }
    });
  }
  return { events, warnings };
}

export function eventIdentity(event) {
  return [event.agentId, event.jobId && `Job ${event.jobId}`,
    event.caseIndex != null && `Case ${typeof event.caseIndex === 'number' ? event.caseIndex + 1 : event.caseIndex}`, event.caseId,
    event.runId && `Run ${event.runId}`].filter(Boolean).join(' · ');
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

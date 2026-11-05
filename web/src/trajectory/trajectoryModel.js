// Pure helpers for the trajectory view; the document is abb.agent-trajectory.v1.

export function stepTitle(step) {
  const tools = (step.tool_logs || []).map(log => log.tool_name).filter(Boolean);
  if (step.kind === 'tool_only') return tools.length ? `Tool: ${tools.join(', ')}` : 'Tool execution';
  const text = step.output?.text;
  if (tools.length) return `Model → ${tools.join(', ')}`;
  if (typeof text === 'string' && text.trim()) return text.trim().replace(/\s+/g, ' ').slice(0, 96);
  if (step.output?.wire_error) return `Model call failed: ${step.output.wire_error.error_code || 'transport error'}`;
  return 'Model call';
}

export function stepTone(step) {
  const logs = step.tool_logs || [];
  if (step.output?.wire_error && step.output_source !== 'framework') return 'issue';
  if (logs.some(log => log.execution_status === 'error')) return 'issue';
  if (logs.some(log => log.execution_status === 'not_observed' || log.link === 'ambiguous')) return 'warning';
  return 'neutral';
}

export function inputSections(trajectory) {
  const steps = trajectory?.steps || [];
  const sections = (trajectory?.inputs || []).map(input => ({
    ordinal: input.ordinal, inputId: input.input_id, prompt: input.prompt, result: input.result,
    fileChanges: input.file_changes || [],
    steps: steps.filter(step => step.input_ordinal === input.ordinal),
  }));
  const unassigned = steps.filter(step => step.input_ordinal == null);
  if (unassigned.length) sections.push({ ordinal: null, inputId: null, prompt: null, result: null, fileChanges: [], steps: unassigned });
  return sections;
}

// How the document reached the reader: the saved contract, or a derivation for a package that never had one.
export function provenanceNote(trajectory) {
  if (trajectory?.derived_on_read) return { tone: 'derived', text: 'Derived on read; this package has no saved trajectory.json' };
  return { tone: 'saved', text: 'Saved trajectory.json' };
}

// Keep polling until the saved file exists: while the attempt runs, and while the route still reports pending.
export function shouldPoll(trajectory, live) {
  return Boolean(live) || trajectory?.status === 'pending';
}

export function coverageNotes(trajectory) {
  const coverage = trajectory?.coverage || {};
  const notes = [`model calls: ${coverage.model_calls || 'unknown'}`, `tool calls: ${coverage.tool_calls || 'unknown'}`,
    `file changes: ${coverage.file_changes || 'unknown'}`];
  if (coverage.ambiguous_links) notes.push(`${coverage.ambiguous_links} ambiguous tool links`);
  if (coverage.unobserved_tool_executions) notes.push(`${coverage.unobserved_tool_executions} emitted tool calls not observed`);
  if (coverage.unlinked_tool_calls) notes.push(`${coverage.unlinked_tool_calls} tool executions without a model call`);
  return notes;
}

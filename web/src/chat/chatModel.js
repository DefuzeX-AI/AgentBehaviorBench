// Pure helpers for the chat page: composer parsing and ATIF step presentation.

export function parseComposer(text, json) {
  if (!json) return text.trim() ? { value: text } : { error: 'Enter a message' };
  try {
    return { value: JSON.parse(text) };
  } catch (error) {
    return { error: `Invalid JSON: ${error.message}` };
  }
}

// Mailbox evidence identifies the turn even when state and trajectory poll separately.
function mailboxTurn(step) {
  const file = step.extra?.abb?.evidence?.find(ref => /^steps\/\d+\/(input|request)\.json$/.test(ref.file));
  return file ? Number(file.file.split('/')[1]) : null;
}

// A child may finish after the parent has returned or another turn has started.
// Follow the recorded delegation, so its reply stays with the originating prompt.
export function delegatedReplies(document) {
  const replies = new Map();
  const children = new Map((document?.subagent_trajectories || []).map(child => [child.trajectory_id, child]));
  let turn;
  for (const step of document?.steps || []) {
    if (step.source === 'user') turn = mailboxTurn(step);
    if (!turn || step.source !== 'agent' || ownerUnknown(step)) continue;
    for (const result of step.observation?.results || []) {
      for (const ref of result.subagent_trajectory_ref || []) {
        const child = children.get(ref.trajectory_id);
        if (!child) continue;
        const last = child.steps?.at(-1);
        const message = last?.source === 'agent' && !ownerUnknown(last) && stepKind(last) === 'assistant'
          && typeof last.message === 'string' ? last.message.trim() : '';
        if (!replies.has(turn)) replies.set(turn, new Map());
        replies.get(turn).set(child.trajectory_id, {
          id: child.trajectory_id, name: child.agent?.name || 'Subagent', message, timestamp: message ? last.timestamp : null,
        });
      }
    }
  }
  return replies;
}

export function clarificationChoices(document) {
  const requests = new Map();
  let turn;
  for (const step of document?.steps || []) {
    if (step.source === 'user') {
      turn = mailboxTurn(step);
    } else if (turn && step.source === 'agent' && step.llm_call_count) {
      requests.delete(turn);
      const calls = step.tool_calls || [];
      const args = calls.find(call => call.function_name === 'ask_clarification')?.arguments;
      if (calls.length === 1 && typeof args?.question === 'string' && args.question.trim()
          && !args.fields?.length && Array.isArray(args.options) && args.options.length
          && args.options.every(option => typeof option === 'string' && option.trim())) {
        requests.set(turn, { question: args.question, context: typeof args.context === 'string' ? args.context : '',
          options: [...new Set(args.options)] });
      }
    }
  }
  return requests;
}

export function stepKind(step) {
  if (step.source === 'user') return 'user';
  if (step.source === 'system') return 'system';
  if (step.tool_calls?.length || (step.observation?.results?.length && !step.message)) return 'tool';
  return 'assistant';
}

export const STEP_TITLES = { user: 'User', system: 'System', tool: 'Tool call', assistant: 'Assistant' };

// Root steps first, then each subagent trajectory with its nesting depth.
export function flattenTrajectory(document) {
  const rows = [];
  const visit = (trajectory, depth) => {
    for (const step of trajectory.steps || []) rows.push({ trajectoryId: trajectory.trajectory_id, agent: trajectory.agent?.name, depth, step });
    for (const child of trajectory.subagent_trajectories || []) visit(child, depth + 1);
  };
  if (document) visit(document, 0);
  return rows;
}

export function trajectoryStats(document) {
  let modelCalls = 0;
  let subagents = 0;
  const visit = (trajectory, depth) => {
    if (depth > 0) subagents += 1;
    for (const step of trajectory.steps || []) modelCalls += step.llm_call_count || 0;
    for (const child of trajectory.subagent_trajectories || []) visit(child, depth + 1);
  };
  if (document) visit(document, 0);
  const issues = document?.extra?.abb?.issues || [];
  return { modelCalls, subagents, issues };
}

// Which of the run's three records hold a step or a tool call's execution:
// the interceptor's wire record, the Agent's exported spans, its ACP messages.
export const SOURCE_TITLES = {
  network: 'Recorded by the model interceptor (logs/network.jsonl)',
  trace: 'Recorded in the spans the Agent exported (otel/spans.jsonl)',
  acp: 'Recorded in the Agent\'s ACP messages (steps/NNNN/acp-events.jsonl)',
};

export function recordSources(item) {
  const sources = item?.extra?.abb?.sources;
  return Array.isArray(sources) ? sources : [];
}

// No record shows which Agent made the step; it stands in the root trajectory.
export function ownerUnknown(step) {
  return step.extra?.abb?.owner === 'unknown';
}

export function stepMarks(step) {
  return step.extra?.abb?.marks || [];
}

// A short description of a step, shown while writing a mark for it.
export function stepSummary(step) {
  const text = typeof step.message === 'string' && step.message.trim() ? step.message
    : step.tool_calls?.map(call => call.function_name).join(', ') || '';
  return { step_id: step.step_id, source: step.source, summary: text.replace(/\s+/g, ' ').slice(0, 160) };
}

export function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('en-US', { hour12: false });
}

export function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('en-US', { hour12: false });
}

export const PHASE_LABELS = {
  starting: 'Starting', ready: 'Ready', busy: 'Agent replying', stopped: 'Stopped', ending: 'Ending', ended: 'Ended',
};

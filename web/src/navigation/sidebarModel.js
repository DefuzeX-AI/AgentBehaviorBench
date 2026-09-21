import { isComplete } from '../suite/model.js';

export function compactIdentity(value, head = 11, tail = 7) {
  const text = String(value || 'Pending');
  if (text.length <= head + tail + 1) return text;
  return `${text.slice(0, head)}…${tail ? text.slice(-tail) : ''}`;
}

function firstPromptLine(item) {
  const prompt = item.title || item.name || item.public_case?.title
    || item.result?.benchmark?.steps?.[0]?.payload
    || item.benchmark?.steps?.[0]?.payload
    || item.result?.input || item.input;
  if (typeof prompt !== 'string') return '';
  return prompt.split(/\r?\n/, 1)[0].replace(/\s+/g, ' ').trim();
}

export function caseNavigationTitle(item) {
  const base = `Case ${(item.case_index ?? 0) + 1}`;
  const prompt = firstPromptLine(item);
  return prompt ? `${base}: ${prompt}` : base;
}

export function suiteNavigationSummary(cases) {
  const total = cases.length;
  const complete = cases.filter(item => isComplete(item.execution_status)).length;
  const judged = cases.filter(item => item.report_received).length;
  const passed = cases.filter(item => item.judge_status === 'pass').length;
  return {
    total,
    complete,
    judged,
    percentage: total ? Math.round((passed / total) * 100) : 0,
  };
}

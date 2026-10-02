import { errorText } from '../suite/model.js';

const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const list = value => Array.isArray(value) ? value : [];
const text = value => typeof value === 'string' && value.trim() ? value.trim() : null;
const scalar = value => text(value) ?? (typeof value === 'number' && Number.isFinite(value) ? String(value) : null);
const firstText = (...values) => values.map(text).find(Boolean) || null;
const verdicts = new Map([
  ['pass', ['Passed', 'pass']], ['issue', ['Issues found', 'issue']],
  ['insufficient_evidence', ['Insufficient evidence', 'caution']], ['unknown', ['Unknown verdict', 'neutral']],
]);

export function judgeLabel(value) {
  const label = scalar(value);
  return label ? label.replace(/[_-]+/g, ' ').replace(/^./, character => character.toUpperCase()) : null;
}

export function judgeTone(value) {
  const status = text(value)?.toLowerCase();
  if (['pass', 'completed', 'complete', 'satisfied'].includes(status)) return 'pass';
  if (['issue', 'fail', 'failed', 'incomplete', 'defective', 'anomaly_observed', 'critical', 'high'].includes(status)) return 'issue';
  if (['insufficient_evidence', 'uncertain', 'partial', 'medium'].includes(status)) return 'caution';
  return 'neutral';
}

function finding(value, index, kind) {
  const item = object(value);
  return {
    id: firstText(item.issue_id, item.gap_id, item.code, item.type) || `${kind}-${index + 1}`,
    title: text(item.title), message: firstText(item.message, item.description, item.reason, value),
    severity: scalar(item.severity), evidence: list(item.evidence_refs), raw: value,
  };
}

function assessmentRow(key, value) {
  return { key, title: judgeLabel(key), status: scalar(value.status),
    confidence: scalar(value.confidence), severity: scalar(value.severity),
    reason: firstText(value.summary, value.reason, value.message),
    reasonCodes: list(value.reason_codes).map(scalar).filter(value => value !== null),
    evidence: list(value.evidence_refs), raw: value };
}

export function judgeReportModel(report) {
  const saved = object(report);
  const extensions = object(saved.extensions);
  const assessment = object(extensions.assessment);
  const status = text(saved.status)?.toLowerCase() || 'unknown';
  const [verdict, tone] = verdicts.get(status) || [judgeLabel(saved.status), 'neutral'];
  const issues = list(saved.issues).map((item, index) => finding(item, index, 'issue'));
  const dimensions = Object.entries(assessment).filter(([, value]) => scalar(object(value).status) !== null)
    .map(([key, value]) => assessmentRow(key, value));
  const steps = list(extensions.step_results).length ? extensions.step_results : list(extensions.steps);
  return {
    status, tone, verdict,
    confidence: scalar(saved.confidence),
    summary: firstText(saved.summary, saved.reason, extensions.summary, extensions.reason),
    issues, gaps: list(saved.evidence_gaps).map((item, index) => finding(item, index, 'gap')),
    dimensions,
    attributions: list(assessment.attributions).map((value, index) => ({
      ...assessmentRow(`cause-${index + 1}`, object(value)),
      title: judgeLabel(object(value).cause) || `Cause ${index + 1}`,
    })),
    steps: steps.map((value, index) => {
      const step = object(value);
      const references = list(step.issues).map(reference => {
        const id = scalar(reference) || firstText(object(reference).issue_id, object(reference).id);
        const matched = issues.find(issue => issue.id === id);
        return { id, message: matched?.message || firstText(object(reference).message, object(reference).description), raw: reference };
      });
      return { id: firstText(step.step_id, step.input_id) || `Step ${index + 1}`,
        status: firstText(step.verdict, step.status), statusLabel: text(step.verdict) ? 'Verdict' : 'Execution',
        reason: firstText(step.summary, step.reason, step.message), issues: references,
        evidence: list(step.evidence_refs), traceStatus: scalar(step.trace_status),
        traceSpans: scalar(step.trace_spans), raw: value };
    }),
    metadata: [
      ['Report ID', saved.report_id], ['SDK run ID', saved.run_id], ['Case ID', extensions.case_id],
      ['Judge', extensions.judge], ['Decided by', extensions.decided_by], ['Model', extensions.model],
      ['Stop reason', saved.stop_reason], ['Report schema', saved.schema_version],
      ['Assessment schema', assessment.schema_version],
    ].filter(([, value]) => scalar(value) !== null).map(([label, value]) => ({ label, value: scalar(value) })),
    raw: report,
  };
}

export function judgeReportUnavailable(item = {}) {
  item = object(item);
  if (item.report_received || item.judge_status || item.judge_delivery_status === 'received') {
    return { type: 'warning', title: 'Judge report unavailable',
      description: 'This attempt records a report, but its contents are unavailable.' };
  }
  const error = item.error || item.result?.error;
  const failedJudge = item.stage === 'judge_failed' || item.judge_delivery_status === 'failed';
  if (error || failedJudge) return {
    type: 'error', title: failedJudge ? 'Judge did not complete' : 'Attempt failed before a Judge report was saved',
    description: error ? errorText(error) : null,
  };
  const status = item.execution_status || item.status;
  if (['cancelled', 'skipped'].includes(status)) return { type: 'info', title: 'No Judge report', description: `Attempt ${status}.` };
  return { type: 'info', title: 'Judge report not received', description: null };
}

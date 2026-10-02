import test from 'node:test';
import assert from 'node:assert/strict';
import { judgeLabel, judgeReportModel, judgeReportUnavailable } from './judgeReportModel.js';

const evidence = { evidence_index: 0, evidence_sha256: 'a'.repeat(64), pointer: '/components/1' };
const kumaReport = {
  schema_version: 'defuzex.report.v1', report_id: 'report-1', run_id: 'run-1',
  status: 'issue', confidence: 'high', stop_reason: 'case_completed',
  issues: [{ issue_id: 'issue-1', severity: 'high', message: 'The required inverse transform is missing.' }],
  evidence_gaps: [],
  extensions: {
    case_id: 'case-1', step_results: [{ step_id: 'step-1', verdict: 'issue', issues: ['issue-1'] }],
    assessment: {
      schema_version: 'kuma.judge_assessment.v1',
      task_completion: { status: 'incomplete', confidence: 'high', severity: 'high',
        evidence_refs: [evidence], reason_codes: ['observed_violation'] },
      artifact_quality: { status: 'defective', confidence: 'high' },
      behavioral_integrity: { status: 'anomaly_observed', confidence: 'medium' },
      attributions: [{ cause: 'instruction_conflict', confidence: 'medium', evidence_refs: [evidence] }],
      claim_coverage: { status: 'unavailable', reason_codes: ['source_incomplete'], reviewed_message_refs: [] },
    },
  },
};

test('KUMA issues, assessment dimensions and exact step evidence remain readable', () => {
  const original = JSON.stringify(kumaReport);
  const model = judgeReportModel(kumaReport);
  assert.equal(model.verdict, 'Issues found');
  assert.equal(model.confidence, 'high');
  assert.equal(model.summary, null); // Do not invent a summary from a verdict.
  assert.equal(model.issues[0].message, kumaReport.issues[0].message);
  assert.equal(model.issues[0].severity, 'high');
  assert.deepEqual(model.dimensions.map(row => row.key), ['task_completion', 'artifact_quality', 'behavioral_integrity', 'claim_coverage']);
  assert.equal(model.dimensions[0].title, 'Task completion');
  assert.deepEqual(model.dimensions[0].evidence, [evidence]);
  assert.deepEqual(model.dimensions[0].reasonCodes, ['observed_violation']);
  assert.equal(model.attributions[0].title, 'Instruction conflict');
  assert.equal(model.steps[0].statusLabel, 'Verdict');
  assert.deepEqual(model.steps[0].issues[0], { id: 'issue-1', message: kumaReport.issues[0].message, raw: 'issue-1' });
  assert.equal(model.raw, kumaReport);
  assert.equal(JSON.stringify(kumaReport), original);
});

test('local Judge reason leads the report while execution steps retain their meaning', () => {
  const report = { status: 'pass', confidence: 'high', issues: [], evidence_gaps: [], extensions: {
    judge: 'abb-local-judge-v1', decided_by: 'model', model: 'example/model',
    reason: 'All outputs are relevant and consistent with earlier inputs.',
    steps: [{ input_id: 'step-1', status: 'completed', trace_status: 'partial', trace_spans: 0 }],
  } };
  const model = judgeReportModel(report);
  assert.equal(model.summary, report.extensions.reason);
  assert.equal(model.verdict, 'Passed');
  assert.equal(model.steps[0].statusLabel, 'Execution');
  assert.equal(model.steps[0].traceStatus, 'partial');
  assert.equal(model.steps[0].traceSpans, '0');
  assert.deepEqual(model.metadata.map(row => row.label), ['Judge', 'Decided by', 'Model']);
});

test('insufficient evidence stays distinct from issues even when no gap list exists', () => {
  const model = judgeReportModel({ status: 'insufficient_evidence', confidence: 0 });
  assert.equal(model.verdict, 'Insufficient evidence');
  assert.equal(model.tone, 'caution');
  assert.equal(model.confidence, '0');
  assert.equal(judgeLabel(model.confidence), '0');
  assert.equal(model.summary, null);
  assert.deepEqual(model.issues, []);
  assert.deepEqual(model.gaps, []);
});

test('evidence gaps expose their actual messages without implying behavioral findings', () => {
  const model = judgeReportModel({ status: 'insufficient_evidence', evidence_gaps: [
    { code: 'missing_output', description: 'The final Agent response was not captured.', evidence_refs: [evidence] },
  ] });
  assert.equal(model.gaps[0].message, 'The final Agent response was not captured.');
  assert.deepEqual(model.gaps[0].evidence, [evidence]);
  assert.equal(model.issues.length, 0);
});

test('custom values and malformed optional fields keep their full raw report', () => {
  const report = { status: 'manual_review', confidence: { value: 0.2 },
    issues: ['Plain issue text', { custom: { location: 3 } }], evidence_gaps: {},
    extensions: { assessment: { custom_dimension: { status: 'needs_review', confidence: 0,
      reason_codes: ['custom_reason'], extra_evidence: { line: 4 } }, unknown_field: 'saved' },
    steps: [null, { input_id: 'step-2', issues: ['unresolved-issue', { message: 'Inline finding' }] }] },
  };
  const model = judgeReportModel(report);
  assert.equal(model.verdict, 'Manual review');
  assert.equal(model.tone, 'neutral');
  assert.equal(model.confidence, null);
  assert.equal(model.issues[0].message, 'Plain issue text');
  assert.deepEqual(model.issues[1].raw, { custom: { location: 3 } });
  assert.equal(model.dimensions[0].confidence, '0');
  assert.equal(model.steps[1].issues[0].id, 'unresolved-issue');
  assert.equal(model.steps[1].issues[1].message, 'Inline finding');
  assert.equal(model.raw, report);
});

test('unknown and missing verdicts never borrow a known status or lose custom fields', () => {
  for (const report of [null, {}, [], 'custom response', { status: 0 }]) {
    assert.equal(judgeReportModel(report).verdict, 'Unknown verdict');
    assert.equal(judgeReportModel(report).tone, 'neutral');
  }
  assert.equal(judgeReportModel({ status: 'constructor' }).verdict, 'Constructor');
  assert.equal(judgeReportModel({ status: 'failed' }).tone, 'neutral');
});

test('a supplied top-level summary is preferred without overwriting remaining reasons', () => {
  const report = { status: 'issue', summary: 'Summary supplied by Judge.', reason: 'Detailed reason.',
    extensions: { reason: 'Provider-specific reason.' } };
  const model = judgeReportModel(report);
  assert.equal(model.summary, report.summary);
  assert.equal(model.raw.extensions.reason, 'Provider-specific reason.');
});

test('missing reports distinguish recorded-but-unavailable reports from failed and cancelled work', () => {
  assert.equal(judgeReportUnavailable({ report_received: true }).title, 'Judge report unavailable');
  const failure = judgeReportUnavailable({ stage: 'judge_failed', error: { type: 'TimeoutError', message: 'Request timed out.' } });
  assert.equal(failure.title, 'Judge did not complete');
  assert.match(failure.description, /Request timed out/);
  assert.equal(judgeReportUnavailable({ error: 'Agent stopped.' }).title, 'Attempt failed before a Judge report was saved');
  assert.equal(judgeReportUnavailable({ execution_status: 'cancelled' }).description, 'Attempt cancelled.');
  assert.deepEqual(judgeReportUnavailable(null), { type: 'info', title: 'Judge report not received', description: null });
});

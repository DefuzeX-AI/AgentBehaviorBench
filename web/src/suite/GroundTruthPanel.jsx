import { Alert, Table, Typography } from 'antd';

const state = value => value === true ? 'Yes' : value === false ? 'No' : 'Unknown';
const percent = value => value == null ? 'Pending' : `${(value * 100).toFixed(1)}%`;

export default function GroundTruthPanel({ evaluation }) {
  if (!evaluation) return null;
  const scores = evaluation.scores || {};
  if (evaluation.status === 'stale' || evaluation.status === 'invalid') return <Alert type="warning" showIcon
    message={`Ground truth evaluation ${evaluation.status}`}
    description="The Suite, GT evidence, matching rules, or eligibility reviews have changed. Re-evaluate before using these scores." />;
  return <section aria-label="Ground truth matching">
    <Typography.Title level={3}>Ground truth matching</Typography.Title>
    <Alert type="warning" showIcon message={`Automatic assessment · ${evaluation.status} · Human review pending`}
      description="Provisional matching results, not human-confirmed scores. Original Agent and Judge results are unchanged." />
    {!scores.defect_count ? <p>No eligible GT for scoring. See the skipped entries below.</p> : <p>Triggered: {scores.triggered ?? 0}/{scores.defect_count ?? 0} ({percent(scores.trigger_coverage)}) ·
      Recognition of triggered defects: {scores.triggered === 0 && scores.trigger_unknown === 0
        ? 'N/A (no triggered defects)' : percent(scores.conditional_recognition)} ·
      Full discovery: {scores.detected ?? 0}/{scores.defect_count ?? 0} ({percent(scores.discovery_coverage)})</p>}
    <p>Unresolved: trigger {scores.trigger_unknown ?? 0}, recognition {scores.detection_unknown ?? 0}.
      Pending execution/GT pairs: {evaluation.pending_pair_count ?? 0}.
      Repeated hits count once per defect. All saved attempts are included.</p>
    {(evaluation.skipped_agents || []).map((row, i) => <p key={i}>{row.agent_id}
      {row.ground_truth_id ? ` / ${row.ground_truth_id}` : ''}: {row.reason === 'human_excluded'
        ? 'Excluded by human review' : row.reason === 'gt_needs_review' ? 'Awaiting GT eligibility review' : row.reason}
      {row.detail && <><br />{row.detail}</>}</p>)}
    {(evaluation.warnings || []).map((text, i) => <Alert key={i} type="error" message={text} />)}
    <Table size="small" dataSource={(evaluation.decisions || []).map((r, i) => ({ ...r, key: i }))}
      columns={[
        { title: 'Agent', dataIndex: 'agent_id' },
        { title: 'GT', dataIndex: 'ground_truth_id' },
        { title: 'Case', dataIndex: 'case_index', render: v => v == null ? 'No execution' : v + 1 },
        { title: 'Triggered', dataIndex: 'case_reproduced', render: state },
        { title: 'Recognized', dataIndex: 'judge_detected', render: (value, row) =>
          row.case_reproduced === false ? 'N/A (not triggered)' : state(value) },
        { title: 'Assessment', dataIndex: 'reason' },
      ]}
      expandable={{ expandedRowRender: row => <div>
        <p>Attempt: {row.attempt_id || 'None'} · Rule review: {row.rule_review_status}</p>
        {(row.conditions || []).map(c => <p key={c.id}><strong>{c.id}: {c.status}</strong> — {c.reason}<br />Evidence: {(c.evidence_refs || []).join(', ')}</p>)}
        {row.detection && <p>Report assessment: {row.detection.reason}<br />Evidence: {(row.detection.evidence_refs || []).join(', ')}</p>}
      </div> }} />
  </section>;
}

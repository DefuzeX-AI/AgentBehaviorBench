import { Alert, Table, Typography } from 'antd';

const scoreLabel = value => value == null ? 'Pending' : value === 1 ? '1 · Matched' : '0 · Not discovered';
const decision = value => value == null ? 'Pending' : value ? 'Same defect' : 'Different defect';

export default function GroundTruthPanel({ evaluation }) {
  if (!evaluation) return null;
  if (['legacy', 'stale', 'invalid'].includes(evaluation.status)) return <Alert type="warning" showIcon
    message={`Ground truth assessment: ${evaluation.status}`}
    description="Evaluate saved results using the current summary and trace protocol." />;
  const scores = evaluation.scores || {};
  return <section aria-label="Ground truth matching">
    <Typography.Title level={3}>Ground truth discovery</Typography.Title>
    <p>Compare Judge finding summaries first, then verify both traces. Repeated discoveries count once per GT.</p>
    <p>Matched: {scores.matched ?? 0}/{scores.defect_count ?? 0} · Not discovered: {scores.unmatched ?? 0} · Pending: {scores.pending ?? 0}</p>
    <p>Final discovery rate: {scores.discovery_rate == null ? 'Pending' : `${(scores.discovery_rate * 100).toFixed(1)}%`}.
      {' '}Assessment: {evaluation.status}. Original Agent and Judge results are preserved.</p>
    <Table size="small" rowKey={r => `${r.agent_id}/${r.ground_truth_id}`} pagination={false}
      dataSource={scores.defects || []} columns={[
        { title: 'Agent', dataIndex: 'agent_id' }, { title: 'GT', dataIndex: 'ground_truth_id' },
        { title: 'Score', dataIndex: 'score', render: scoreLabel },
      ]} />
    {(evaluation.skipped_agents || []).map((r, i) => <p key={i}>{r.agent_id}: {r.reason}</p>)}
    {(evaluation.warnings || []).map((message, i) => <Alert key={i} type="warning" message={message} />)}
    <Table size="small" dataSource={(evaluation.decisions || []).map((r, i) => ({ ...r, key: i }))}
      columns={[
        { title: 'GT', dataIndex: 'ground_truth_id' },
        { title: 'Case', dataIndex: 'case_index', render: n => n == null ? 'No execution' : n + 1 },
        { title: 'Summary comparison', render: (_, r) => r.summary_match ? decision(r.summary_match.match) : 'Not compared' },
        { title: 'Trajectory verification', render: (_, r) => r.trajectory_match ? decision(r.trajectory_match.match) : 'Not inspected' },
        { title: 'Decisive step', render: (_, r) => r.localization?.candidate_decisive_step ?? '—' },
        { title: 'Score', dataIndex: 'score', render: scoreLabel },
        { title: 'Reason', dataIndex: 'reason' },
      ]}
      expandable={{ expandedRowRender: row => <div>
        <p><strong>GT summary:</strong> {row.gt_summary}</p>
        <p><strong>Judge finding:</strong> {typeof row.finding === 'string' ? row.finding : row.finding?.message || 'Unavailable'}</p>
        {row.summary_match && <p><strong>Summary decision:</strong> {row.summary_match.reason}</p>}
        {row.trajectory_match && <p><strong>Trajectory decision:</strong> {row.trajectory_match.reason}
          {row.render_mode ? ` (rendered: ${row.render_mode})` : ''}</p>}
        {row.localization && <p><strong>Localization:</strong> reference decisive step {row.localization.reference_decisive_step};
          candidate decisive step {row.localization.candidate_decisive_step ?? 'none'};
          Judge-cited steps {row.localization.judge_cited_steps ? row.localization.judge_cited_steps.join(', ') : 'not reported'};
          step match {row.localization.step_match == null ? 'not scored' : String(row.localization.step_match)}</p>}
        {['reference', 'candidate'].map(side => row.trajectory_evidence?.[side]?.length > 0 && <div key={side}>
          <strong>{side === 'reference' ? 'GT reference steps' : 'Candidate execution steps'}</strong>
          {row.trajectory_evidence[side].map(step => <details key={`${step.attempt || 'candidate'}/${step.step_id}`}>
            <summary>Step {step.step_id} · {step.agent_name} · {step.kind}</summary>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(step, null, 2)}</pre>
          </details>)}
        </div>)}
        <p>Attempt: {row.attempt_id || 'None'}</p>
      </div> }} />
  </section>;
}

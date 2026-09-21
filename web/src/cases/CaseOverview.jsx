import { Alert, Descriptions, Progress, Statistic, Tag, Typography } from 'antd';
import { executionLabels } from '../suite/model.js';

const { Paragraph, Text, Title } = Typography;
const stateColor = value => ['succeeded', 'complete', 'completed', 'committed', 'received', 'captured'].includes(value) ? 'success'
  : ['failed', 'rejected', 'missing'].includes(value) ? 'error' : value ? 'processing' : 'default';

export default function CaseOverview({ item, attempt, data, error }) {
  const manifest = data?.manifest || {};
  const publicCase = data?.case?.extensions?.official_case?.public_case || {};
  const stages = [['Execution', manifest.execution || item.execution_status], ['OTel', manifest.otel],
    ['Submission', manifest.submission], ['Judge', manifest.judge || item.judge_status], ['Evidence', manifest.evidence]];
  const finished = stages.filter(([, value]) => ['succeeded', 'complete', 'completed', 'committed', 'received', 'captured'].includes(value)).length;
  return <div className="case-overview">
    {error && <Alert type="warning" showIcon message="Case artifacts are temporarily unavailable" description={error} />}
    <div className="case-stage-strip">{stages.map(([label, value]) => <div key={label}><Text type="secondary">{label}</Text><Tag color={stateColor(value)}>{value || 'Not provided'}</Tag></div>)}</div>
    <div className="case-overview-grid">
      <section className="case-summary-card"><Text className="case-eyebrow">CASE SUMMARY</Text><Title level={3}>{publicCase.title || `Case ${item.case_index + 1}`}</Title>
        <Paragraph>{publicCase.description || item.description || 'The Case description has not been included in the saved public artifact.'}</Paragraph>
        <Descriptions size="small" column={1} items={[
          { key: 'agent', label: 'Agent', children: item.agent_id },
          { key: 'case', label: 'Case ID', children: <Text copyable code>{item.case_id || 'Pending'}</Text> },
          { key: 'run', label: 'Artifact run', children: <Text copyable code>{attempt?.artifact_run_id || 'Not created'}</Text> },
          { key: 'strategy', label: 'Strategy', children: publicCase.strategy_id || data?.case?.extensions?.official_case?.executed_strategy_group?.strategy_group_id || 'Not recorded' },
          { key: 'execution', label: 'Execution', children: executionLabels[item.execution_status] || item.execution_status },
        ]} />
      </section>
      <section className="case-readiness-card"><Statistic title="Recorded steps" value={data?.inputs?.length || manifest.steps?.length || 0} />
        <Progress percent={Math.round((finished / stages.length) * 100)} strokeColor="#2f6d51" />
        <Text type="secondary">Artifact pipeline completeness</Text>
      </section>
    </div>
    {data && !data.judge && <Alert type="info" showIcon message="No Judge report has been produced" description="Execution data is retained. Judge remains separate from execution status." />}
  </div>;
}

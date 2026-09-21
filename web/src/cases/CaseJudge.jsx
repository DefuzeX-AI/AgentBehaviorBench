import { Alert, Descriptions, Empty, List, Tag, Typography } from 'antd';

const { Paragraph, Text, Title } = Typography;

function FindingList({ title, items, empty }) {
  return <section className="judge-findings"><Title level={4}>{title}</Title>{items?.length ? <List bordered dataSource={items}
    renderItem={(item, index) => <List.Item><div><Text strong>{item.code || item.type || `Finding ${index + 1}`}</Text><Paragraph>{item.message || item.description || JSON.stringify(item)}</Paragraph></div></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty} />}</section>;
}

export default function CaseJudge({ report, item }) {
  if (!report) return <Alert type="info" showIcon message="Judge report not received" description="The Case execution may still be valid. Judge generation and host acceptance are tracked independently." />;
  const rejected = item.host_accepted === false || item.host_acceptance === false || item.host_acceptance === 'rejected';
  return <div className="judge-report">
    {rejected && <Alert type="warning" showIcon message="The host rejected this execution" description="The original Judge report is retained for diagnosis, but it does not count as an accepted benchmark result." />}
    <div className="judge-verdict"><div><Text className="case-eyebrow">JUDGE VERDICT</Text><Title level={2}>{report.status || 'Unknown'}</Title></div>
      <Tag color={report.status === 'pass' ? 'success' : 'warning'}>{report.confidence ? `${report.confidence} confidence` : 'Confidence not recorded'}</Tag></div>
    <Descriptions bordered size="small" column={{ xs: 1, sm: 2 }} items={[
      { key: 'report', label: 'Report ID', children: <Text copyable code>{report.report_id || 'Not recorded'}</Text> },
      { key: 'run', label: 'SDK run ID', children: <Text copyable code>{report.run_id || 'Not recorded'}</Text> },
      { key: 'stop', label: 'Stop reason', children: report.stop_reason || 'Not recorded' },
      { key: 'steps', label: 'Step results', children: report.extensions?.step_results?.length || 0 },
    ]} />
    <FindingList title="Issues" items={report.issues} empty="No behavioral issues reported" />
    <FindingList title="Evidence gaps" items={report.evidence_gaps} empty="No evidence gaps reported" />
  </div>;
}

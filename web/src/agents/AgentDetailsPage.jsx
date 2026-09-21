import { useState } from 'react';
import { Alert, Breadcrumb, Button, Card, Descriptions, Empty, Skeleton, Statistic, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import useLiveJson from '../useLiveJson.js';
import { agentSummaries } from '../suite/summaryModel.js';
import CaseCardGrid from '../suite/CaseCardGrid.jsx';
import './agents.css';

export default function AgentDetailsPage({ agentId, endpoint, snapshot, cases, onBack, onCaseSelect }) {
  const profile = useLiveJson(`${endpoint}/agents/${encodeURIComponent(agentId)}`, agentId, false);
  const data = profile.data?.agent_id === agentId ? profile.data : null;
  const items = cases.filter(item => item.agent_id === agentId);
  const summary = agentSummaries(items, snapshot?.jobs || [])[0];
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const repository = /^https:\/\//i.test(data?.repository || '') ? data.repository : null;
  return <section className="agent-details" aria-label="Agent overview">
    <Breadcrumb items={[{ title: <Button type="link" onClick={onBack}>Suite overview</Button> }, { title: agentId }]} />
    <header className="agent-intro-header"><Typography.Text type="secondary">AGENT OVERVIEW</Typography.Text>
      <Typography.Title level={1}>{data?.display_name || agentId}</Typography.Title>
      <Typography.Text copyable>{agentId}</Typography.Text>
    </header>
    {data && <Card title="Strategy Group" className="agent-strategy-card">
      {data.strategy_group ? <>
        <Typography.Title level={2}>{data.strategy_group.id} <Typography.Text type="secondary">Version {data.strategy_group.version}</Typography.Text></Typography.Title>
        <Typography.Paragraph type="secondary">Declared in the current requirement.md. Historical Case selections are recorded separately.</Typography.Paragraph>
        <Typography.Paragraph copyable={{ text: `strategy_group:\n  schema_version: ${data.strategy_group.schema_version}\n  id: ${data.strategy_group.id}\n  version: "${data.strategy_group.version}"` }}>
          <Typography.Text code>{data.strategy_group.schema_version}</Typography.Text>
        </Typography.Paragraph>
      </> : <Typography.Text type="secondary">{data.profile_warning || 'No explicit Strategy Group declared. The selected SDK determines its default.'}</Typography.Text>}
    </Card>}
    <div className="agent-metrics">
      <Card><Statistic title="Cases in this Suite" value={items.length} /></Card>
      <Card><Statistic title="Execution complete" value={summary?.completed || 0} /></Card>
      <Card><Statistic title="Judge reports" value={summary?.judged || 0} /></Card>
      <Card><Statistic title="Judge pass" value={summary?.passed || 0} /></Card>
    </div>
    {data ? <Card title="About this Agent" extra={<Typography.Text type="secondary">{data.provenance}</Typography.Text>}>
      <Descriptions column={{ xs: 1, sm: 2 }} items={[
        { key: 'framework', label: 'Framework', children: data.framework || 'Not recorded' },
        { key: 'runtime', label: 'Runtime', children: data.runtime || 'Not recorded' },
        { key: 'repository', label: 'Source', children: repository ? <a href={repository} target="_blank" rel="noreferrer">{repository}</a> : 'Local source' },
        { key: 'revision', label: 'Source revision', children: <Typography.Text code>{data.revision || 'Not recorded'}</Typography.Text> },
      ]} />
      <div className="agent-description">{data.description ? <ReactMarkdown skipHtml components={{ img: () => null }}>{data.description}</ReactMarkdown> : <Typography.Text type="secondary">No Agent description available.</Typography.Text>}</div>
    </Card> : profile.error ? <Alert type="info" showIcon message="Agent introduction is unavailable" description="The local profile may have been moved or removed. Saved Cases remain available below." /> : <Skeleton active />}
    <div><Typography.Title level={2}>Cases</Typography.Title><Typography.Paragraph type="secondary">Select a Case to inspect its execution, evidence and Judge report.</Typography.Paragraph></div>
    {items.length ? <CaseCardGrid cases={items} page={page} pageSize={pageSize} onSelect={onCaseSelect} onPage={(next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size); }} /> : <Empty description="No Cases have been recorded yet." />}
  </section>;
}

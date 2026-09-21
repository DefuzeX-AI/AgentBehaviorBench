import { Alert, Button, Descriptions, Empty, Skeleton, Table, Tabs, Tag, Typography } from 'antd';
import { ArrowRightOutlined, LinkOutlined, RobotOutlined } from '@ant-design/icons';
import SuiteBreadcrumb from '../navigation/SuiteBreadcrumb.jsx';
import { caseNavigationTitle } from '../navigation/sidebarModel.js';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import useLiveJson from '../useLiveJson.js';
import { agentSummaries } from '../suite/summaryModel.js';
import { ExecutionBadge, JudgeBadge } from '../suite/CaseStatus.jsx';
import './agents.css';

const { Text, Title } = Typography;

export default function AgentDetailsPage({ agentId, endpoint, snapshot, cases, onBack, onCaseSelect }) {
  const profile = useLiveJson(`${endpoint}/agents/${encodeURIComponent(agentId)}`, agentId, false);
  const data = profile.data?.agent_id === agentId ? profile.data : null;
  const items = cases.filter(item => item.agent_id === agentId);
  const summary = agentSummaries(items, snapshot?.jobs || [])[0];
  const repository = /^https:\/\//i.test(data?.repository || '') ? data.repository : null;
  const check = data?.strategy_check;
  const group = data?.strategy_group;
  const state = check?.status || 'unverified';
  const issues = items.filter(item => item.judge_status === 'issue').length;
  const intro = (data?.description || '').replace(/^#{1,6}\s+.*$/gm, '').trim().split(/\n\s*\n/)[0] || '';
  const brief = intro.replace(/\s+/g, ' ').trim();
  const metadata = <Descriptions bordered size="small" column={1} items={[
    { key: 'id', label: 'Agent ID', children: agentId },
    { key: 'framework', label: 'Framework', children: data?.framework || 'Not recorded' },
    { key: 'runtime', label: 'Runtime', children: data?.runtime || 'Not recorded' },
    { key: 'repository', label: 'Source', children: repository ? <a href={repository} target="_blank" rel="noreferrer">{repository}</a> : 'Local source' },
    { key: 'revision', label: 'Source revision', children: <code>{data?.revision || 'Not recorded'}</code> },
    { key: 'strategy', label: 'Strategy Group', children: group ? `${group.id} · v${group.version}` : 'Not declared' },
    { key: 'schema', label: 'Strategy schema', children: group?.schema_version || 'Not recorded' },
  ]} />;
  const missingProfile = profile.error
    ? <Alert type="info" showIcon message="Local Agent profile unavailable" description="Saved Case results remain available." />
    : <Skeleton active paragraph={{ rows: 3 }} />;
  const columns = [
    { title: 'Case', key: 'case', width: 105, render: (_, item) => <Button className="agent-case-link" type="link" onClick={() => onCaseSelect(item)}>Case {item.case_index + 1}</Button> },
    { title: 'Task', key: 'task', render: (_, item) => <div className="agent-task-text">{item.description || (caseNavigationTitle(item).includes(': ') ? caseNavigationTitle(item).split(': ').slice(1).join(': ') : 'Open Case to inspect the recorded task.')}</div> },
    { title: 'Execution', key: 'execution', width: 160, render: (_, item) => <ExecutionBadge status={item.execution_status} /> },
    { title: 'Judge', key: 'judge', width: 180, render: (_, item) => <div className="agent-judge-result"><JudgeBadge status={item.judge_status} />{(item.host_accepted === false || item.host_acceptance === 'rejected') && <Text type="danger">Host rejected</Text>}</div> },
    { title: 'Attempts', dataIndex: 'attempts', key: 'attempts', width: 90, render: attempts => attempts?.length || 0 },
    { title: '', key: 'open', width: 48, render: (_, item) => <Button type="text" icon={<ArrowRightOutlined />} aria-label={`Open Case ${item.case_index + 1}`} onClick={() => onCaseSelect(item)} /> },
  ];
  return <section className="agent-details" aria-label="Agent overview">
    <SuiteBreadcrumb agentId={agentId} onSuiteSelect={onBack} />
    <header className="agent-intro-header">
      <div className="agent-profile-avatar"><RobotOutlined /></div>
      <div className="agent-intro-main"><div className="agent-title-line"><Title level={1}>{data?.display_name || agentId}</Title><div>{data?.framework && <Tag>{data.framework}</Tag>}{data?.runtime && <Tag>{data.runtime}</Tag>}</div></div>
        <p className="agent-brief">{brief ? brief.length > 240 ? brief.slice(0, 237) + '…' : brief : 'Agent evaluation results in this Suite.'}</p>
      </div>
      {repository && <Button href={repository} target="_blank" rel="noreferrer" icon={<LinkOutlined />}>Repository</Button>}
    </header>
    <section className="agent-result-strip" aria-label="Results in this Suite">
      <div className="agent-result-context">THIS SUITE<span>Evaluation results</span></div>
      {[
        ['Cases', items.length, ''], ['Completed', summary?.completed || 0, ''],
        ['Judge reports', summary?.judged || 0, ''], ['Judge pass', summary?.passed || 0, 'pass'], ['Judge issues', issues, issues ? 'issue' : ''],
      ].map(([label, value, tone]) => <div className={`agent-result-metric ${tone}`} key={label}><strong>{value}</strong><span>{label}</span></div>)}
    </section>
    {data ? <section className={`agent-strategy-strip ${state === 'invalid' ? 'invalid' : ''}`} aria-label="Strategy Group">
      <div className="agent-strategy-main"><span className="agent-section-label">STRATEGY GROUP <span>Current local configuration</span></span>
        <div className="agent-strategy-title"><h2>{check?.display_name || group?.id || 'No explicit selection'}</h2><Tag color={state === 'valid' ? 'success' : state === 'invalid' ? 'error' : 'warning'}>{state === 'valid' ? 'Catalog valid' : state === 'invalid' ? 'Invalid' : 'Unverified'}</Tag></div>
        {group && <span className="agent-strategy-coordinate">{group.id} <span>· v{group.version}</span></span>}
        {(check?.reason || data.profile_warning) && <p className="agent-strategy-warning">{check?.reason || data.profile_warning}</p>}
      </div>
      <div className="agent-strategy-aside"><span>{check ? `Checked by ${check.sdk}` : 'No catalog check recorded'}</span>{check?.checked_at && <time>{new Date(check.checked_at).toLocaleString()}</time>}
        <details><summary>Validation details</summary><p>Catalog validity is separate from the Judge verdict. This is the current local profile; historical Cases retain their executed selection.</p>{group && <code>{group.schema_version}</code>}</details>
      </div>
    </section> : missingProfile}
    <Tabs className="agent-content-tabs" defaultActiveKey="cases" items={[
      { key: 'cases', label: `Cases (${items.length})`, children: <section aria-label="Agent Cases"><div className="agent-section-heading"><h2>Cases in this Suite</h2><Text type="secondary">Inspect each task, execution and Judge result.</Text></div>
        {items.length ? <Table className="agent-cases-table" size="middle" rowKey="key" tableLayout="fixed" columns={columns} dataSource={items} scroll={{ x: 820 }} pagination={items.length > 10 ? { defaultPageSize: 10, showSizeChanger: true } : false} /> : <Empty description="No Cases have been recorded yet" />}</section> },
      { key: 'about', label: 'About Agent', children: data ? <div className="agent-description"><Text type="secondary">Current local Agent profile</Text>{data.description ? <ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={{ img: () => null }}>{data.description}</ReactMarkdown> : <Empty description="No Agent description available" />}</div> : missingProfile },
      { key: 'configuration', label: 'Configuration', children: data ? <section className="agent-configuration"><div className="agent-section-heading"><h2>Local configuration</h2><Text type="secondary">Current source and runtime settings. These may differ from earlier executions.</Text></div>{metadata}</section> : missingProfile },
    ]} />
  </section>;
}

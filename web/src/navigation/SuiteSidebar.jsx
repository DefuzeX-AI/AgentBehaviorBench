import {
  DownOutlined,
  InsertRowLeftOutlined,
  MenuFoldOutlined,
  ReloadOutlined,
  RightOutlined,
  SearchOutlined,
  SwitcherOutlined,
} from '@ant-design/icons';
import { Button, Input, Skeleton, Tag, Tooltip, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { isActive, needsAttention, normalizeCases } from '../suite/model.js';
import { caseNavigationTitle, compactIdentity, suiteNavigationSummary } from './sidebarModel.js';
import { ExecutionBadge } from '../suite/CaseStatus.jsx';
import './navigation.css';

const judgeColor = status => status === 'pass' ? 'success'
  : status === 'issue' || status === 'insufficient_evidence' ? 'warning' : 'default';

function Chevron({ expanded }) {
  return expanded ? <DownOutlined /> : <RightOutlined />;
}

function CaseItem({ item, selected, onSelect }) {
  const status = item.judge_status || (needsAttention(item.execution_status) ? item.execution_status : null);
  return <button type="button" className={`suite-nav-case${isActive(item.execution_status) ? ' is-running' : ''}${selected ? ' selected' : ''}`} onClick={() => onSelect(item)}>
    <span className="suite-nav-case-copy" title={caseNavigationTitle(item)}>
      <strong>{caseNavigationTitle(item)}</strong>
      <small title={item.case_id}>{compactIdentity(item.case_id, 16, 0)}</small>
    </span>
    {isActive(item.execution_status) ? <ExecutionBadge status={item.execution_status} /> : status && <Tag color={item.judge_status ? judgeColor(status) : 'error'}>{status}</Tag>}
  </button>;
}

export default function SuiteSidebar({ snapshot, selectedCaseKey, busy, error, onSuiteSelect, onCaseSelect, onRefresh }) {
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState('');
  const [suiteExpanded, setSuiteExpanded] = useState(true);
  const [expandedAgents, setExpandedAgents] = useState({});
  const cases = useMemo(() => normalizeCases(snapshot), [snapshot]);
  const summary = suiteNavigationSummary(cases);
  const suiteId = snapshot?.suite_id || 'Loading Suite';
  const normalizedQuery = query.trim().toLowerCase();

  useEffect(() => {
    if (!snapshot?.jobs) return;
    setExpandedAgents(previous => Object.fromEntries(snapshot.jobs.map(job => [job.agent_id, previous[job.agent_id] ?? true])));
  }, [snapshot?.jobs]);

  const jobs = useMemo(() => (snapshot?.jobs || []).map(job => {
    const agentCases = cases.filter(item => item.agent_id === job.agent_id);
    if (!normalizedQuery || job.agent_id.toLowerCase().includes(normalizedQuery)) return { ...job, visibleCases: agentCases };
    const visibleCases = agentCases.filter(item => [item.case_id, caseNavigationTitle(item), item.judge_status, item.execution_status]
      .some(value => String(value || '').toLowerCase().includes(normalizedQuery)));
    return { ...job, visibleCases };
  }).filter(job => !normalizedQuery || job.agent_id.toLowerCase().includes(normalizedQuery) || job.visibleCases.length), [cases, normalizedQuery, snapshot?.jobs]);

  if (collapsed) return <aside className="sidebar suite-sidebar suite-sidebar-collapsed" aria-label="Suite navigation">
    <div className="suite-collapsed-nav">
      <Tooltip title="Expand sidebar" placement="right"><Button type="text" icon={<InsertRowLeftOutlined />} onClick={() => setCollapsed(false)} aria-label="Expand sidebar" /></Tooltip>
      <Tooltip title="All Suites overview" placement="right"><Button type="text" icon={<SwitcherOutlined />} onClick={onSuiteSelect} aria-label="All Suites overview" /></Tooltip>
      <i className="suite-collapsed-divider" />
      <Tooltip title={suiteId} placement="right"><button type="button" className="suite-collapsed-suite selected" onClick={onSuiteSelect} aria-label={`Open ${suiteId}`}>S</button></Tooltip>
    </div>
    <span className="suite-collapsed-spacer" />
    <Tooltip title="Refresh" placement="right"><Button type="text" icon={<ReloadOutlined spin={busy} />} onClick={onRefresh} aria-label="Refresh Suite" /></Tooltip>
  </aside>;

  return <aside className="sidebar suite-sidebar" aria-label="Suite navigation">
    <header className="suite-sidebar-header">
      <div><Typography.Text type="secondary">RESULTS</Typography.Text><h2>Benchmarks</h2></div>
      <span>
        <Tooltip title="Refresh"><Button size="small" icon={<ReloadOutlined spin={busy} />} onClick={onRefresh}>Refresh</Button></Tooltip>
        <Tooltip title="Collapse sidebar"><Button size="small" type="text" icon={<MenuFoldOutlined />} onClick={() => setCollapsed(true)} aria-label="Collapse sidebar" /></Tooltip>
      </span>
    </header>

    <div className="suite-sidebar-search"><Input allowClear size="small" prefix={<SearchOutlined />} value={query}
      onChange={event => setQuery(event.target.value)} placeholder="Filter Agents or Cases" aria-label="Filter Agents or Cases" /></div>

    <div className="suite-sidebar-label"><Typography.Text type="secondary">SUITES ({snapshot ? 1 : 0})</Typography.Text></div>
    {error && <p role="alert" className="sidebar-error">{error}</p>}
    {!snapshot ? <Skeleton active paragraph={{ rows: 6 }} /> : <nav className="suite-nav" aria-label="Suite, Agent, and Case results">
      <div className="suite-nav-root selected">
        <button type="button" className="suite-nav-chevron" onClick={() => setSuiteExpanded(value => !value)} aria-label={`${suiteExpanded ? 'Collapse' : 'Expand'} Suite`}><Chevron expanded={suiteExpanded} /></button>
        <button type="button" className="suite-nav-root-content" onClick={onSuiteSelect}>
          <span className="suite-nav-root-heading"><strong>Suite</strong><code>{compactIdentity(suiteId, 7, 4)}</code>
            <b className={summary.percentage === 100 ? 'pass-high' : summary.percentage >= 70 ? 'pass-mid' : 'pass-low'}>{summary.percentage}%</b></span>
          <small title={suiteId}>{compactIdentity(suiteId, 12, 9)}</small>
          <span className="suite-nav-root-stats">{summary.complete}/{summary.total} complete <i /> {summary.judged}/{summary.total} judged</span>
        </button>
      </div>

      {suiteExpanded && <div className="suite-nav-agents">
        {jobs.map(job => {
          const expanded = expandedAgents[job.agent_id] ?? true;
          return <section className="suite-nav-agent" key={job.agent_id}>
            <button type="button" className="suite-nav-agent-heading" onClick={() => setExpandedAgents(previous => ({ ...previous, [job.agent_id]: !expanded }))}>
              <Chevron expanded={expanded} /><strong>{job.agent_id}</strong><span>{job.visibleCases.length} {job.visibleCases.length === 1 ? 'Case' : 'Cases'}</span>
            </button>
            {expanded && <div className="suite-nav-cases">
              {job.visibleCases.map(item => <CaseItem key={item.key} item={item} selected={selectedCaseKey === item.key} onSelect={onCaseSelect} />)}
              {!job.visibleCases.length && <Typography.Text type="secondary" className="suite-nav-empty">No matching Cases</Typography.Text>}
            </div>}
          </section>;
        })}
        {!jobs.length && <Typography.Text type="secondary" className="suite-nav-empty">No matching results</Typography.Text>}
      </div>}
    </nav>}
  </aside>;
}

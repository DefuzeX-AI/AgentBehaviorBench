import { DownOutlined, RightOutlined } from '@ant-design/icons';
import { Skeleton, Tag, Tooltip, Typography } from 'antd';
import { useMemo, useState } from 'react';
import useLiveJson from '../useLiveJson.js';
import { isActive, needsAttention, normalizeCases } from '../suite/model.js';
import { ExecutionBadge } from '../suite/CaseStatus.jsx';
import { caseNavigationTitle, compactIdentity, suiteNavigationSummary } from './sidebarModel.js';
import { suiteCatalogMatches } from './suiteCatalog.js';
import { suiteRouteHref } from './suiteRoute.js';

const judgeColor = status => status === 'pass' ? 'success'
  : status === 'issue' || status === 'insufficient_evidence' ? 'warning' : 'default';

function Chevron({ expanded }) {
  return expanded ? <DownOutlined /> : <RightOutlined />;
}

function CaseItem({ item, selected, onSelect, href }) {
  const status = item.judge_status || (needsAttention(item.execution_status) ? item.execution_status : null);
  const Element = href ? 'a' : 'button';
  return <Element type={href ? undefined : 'button'} href={href}
    className={`suite-nav-case${isActive(item.execution_status) ? ' is-running' : ''}${selected ? ' selected' : ''}`}
    onClick={href ? undefined : () => onSelect(item)}>
    <span className="suite-nav-case-copy" title={caseNavigationTitle(item)}>
      <strong>{caseNavigationTitle(item)}</strong>
      <small title={item.case_id}>{compactIdentity(item.case_id, 16, 0)}</small>
    </span>
    {isActive(item.execution_status) ? <ExecutionBadge status={item.execution_status} /> : status && <Tag color={item.judge_status ? judgeColor(status) : 'error'}>{status}</Tag>}
  </Element>;
}

export default function SuiteNavEntry({ row, snapshot, selected, selectedCaseKey, query, revision, onSuiteSelect, onCaseSelect }) {
  const [expanded, setExpanded] = useState(false);
  const [expandedAgents, setExpandedAgents] = useState({});
  // Other Suites load their Case trees only while expanded, independently of the main view.
  const remote = useLiveJson(expanded && !selected ? `/api/suites/${encodeURIComponent(row.suite_id)}/result` : null, revision);
  const data = selected ? snapshot : remote.data;
  const cases = useMemo(() => normalizeCases(data), [data]);
  const total = row.counts?.planned || 0;
  const complete = row.counts?.completed || 0;
  const summary = data ? suiteNavigationSummary(cases) : {
    total, complete, judged: row.counts?.judge_received || 0,
    percentage: total ? Math.round(complete / total * 100) : 0,
  };
  const jobs = useMemo(() => (data?.jobs || []).map(job => {
    const agentCases = cases.filter(item => item.agent_id === job.agent_id);
    if (!query || job.agent_id.toLowerCase().includes(query)) return { ...job, visibleCases: agentCases };
    const visibleCases = agentCases.filter(item => [item.case_id, caseNavigationTitle(item), item.judge_status, item.execution_status]
      .some(value => String(value || '').toLowerCase().includes(query)));
    return { ...job, visibleCases };
  }).filter(job => !query || job.agent_id.toLowerCase().includes(query) || job.visibleCases.length), [cases, query, data?.jobs]);

  if (query && !suiteCatalogMatches(row, query) && !jobs.length) return null;
  const RootContent = selected ? 'button' : 'a';
  return <section>
    <div className={`suite-nav-root${selected ? ' selected' : ''}`}>
      <button type="button" className="suite-nav-chevron" onClick={() => setExpanded(value => !value)}
        aria-label={`${expanded ? 'Collapse' : 'Expand'} Suite ${row.suite_id}`} aria-expanded={expanded}>
        <Chevron expanded={expanded} />
      </button>
      <RootContent type={selected ? 'button' : undefined} className="suite-nav-root-content"
        href={selected ? undefined : row.url} onClick={selected ? onSuiteSelect : undefined}
        aria-label={`Open Suite ${row.suite_id}`} aria-current={selected ? 'page' : undefined}>
        <span className="suite-nav-root-heading"><strong>Suite</strong><code title={row.suite_id}>{compactIdentity(row.suite_id, 7, 4)}</code>
          <Tooltip title={`Execution complete: ${summary.complete}/${summary.total} Cases`}>
            <b aria-label={`Execution complete: ${summary.percentage}%`} className={summary.percentage === 100 ? 'completion-full' : summary.percentage > 0 ? 'completion-active' : 'completion-pending'}>{summary.percentage}%</b>
          </Tooltip></span>
        <small title={row.suite_id}>{compactIdentity(row.suite_id, 12, 9)}</small>
        <span className="suite-nav-root-stats">{summary.complete}/{summary.total} complete <i /> {summary.judged}/{summary.total} judged</span>
      </RootContent>
    </div>
    {expanded && <div className="suite-nav-agents">
      {row.origin_suite_id && <span className="suite-nav-description" title={row.origin_suite_id}>Reused from {compactIdentity(row.origin_suite_id, 9, 5)}</span>}
      {remote.error && <p role="alert" className="sidebar-error">{remote.error}</p>}
      {!data && !remote.error ? <Skeleton active title={false} paragraph={{ rows: 2 }} /> : jobs.map(job => {
        const agentExpanded = expandedAgents[job.agent_id] ?? true;
        return <section className="suite-nav-agent" key={job.agent_id}>
          <button type="button" className="suite-nav-agent-heading" aria-expanded={agentExpanded}
            onClick={() => setExpandedAgents(previous => ({ ...previous, [job.agent_id]: !agentExpanded }))}>
            <Chevron expanded={agentExpanded} /><strong>{job.agent_id}</strong><span>{job.visibleCases.length} {job.visibleCases.length === 1 ? 'Case' : 'Cases'}</span>
          </button>
          {agentExpanded && <div className="suite-nav-cases">
            {job.visibleCases.map(item => <CaseItem key={item.key} item={item} selected={selected && selectedCaseKey === item.key}
              onSelect={onCaseSelect} href={selected ? undefined : suiteRouteHref(item, 'overview', { pathname: row.url, search: '' })} />)}
            {!job.visibleCases.length && <Typography.Text type="secondary" className="suite-nav-empty">No matching Cases</Typography.Text>}
          </div>}
        </section>;
      })}
      {data && !jobs.length && <Typography.Text type="secondary" className="suite-nav-empty">No matching results</Typography.Text>}
    </div>}
  </section>;
}

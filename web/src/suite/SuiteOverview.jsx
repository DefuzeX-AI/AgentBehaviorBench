import { useMemo } from 'react';
import { AppstoreOutlined, TableOutlined } from '@ant-design/icons';
import { Alert, Button, Input, Progress, Segmented, Select, Space, Statistic, Switch, Table, Tooltip, Typography } from 'antd';
import { useDispatch, useSelector } from 'react-redux';
import { actions } from './store.js';
import { countCases, executionLabels, isActive, normalizeCases } from './model.js';
import { filterCases, latestTimestamp, sortCases } from './tableModel.js';
import CaseStatus, { JudgeBadge } from './CaseStatus.jsx';
import { ExportReportButton } from './SuiteControls.jsx';
import AgentSummaryCards from './AgentSummaryCards.jsx';
import CaseCardGrid from './CaseCardGrid.jsx';
import SuiteActivity from './SuiteActivity.jsx';
import './suite.css';

const { Text, Title } = Typography;

function Metric({ value, label, tone }) {
  return <div className={`suite-metric suite-metric-${tone || 'neutral'}`}>
    <Statistic value={value} title={label} />
  </div>;
}

export default function SuiteOverview({ onCaseSelect, onAgentSelect }) {
  const dispatch = useDispatch();
  const { snapshot, error, updated, filters, table } = useSelector(state => state.suite);
  const cases = useMemo(() => normalizeCases(snapshot), [snapshot]);
  const counts = useMemo(() => countCases(cases), [cases]);
  const visible = useMemo(() => sortCases(filterCases(cases, filters), table.field, table.order), [cases, filters, table.field, table.order]);
  const agents = useMemo(() => [...new Set(cases.map(item => item.agent_id))].sort(), [cases]);
  const statuses = useMemo(() => [...new Set(cases.map(item => item.execution_status))].sort(), [cases]);
  const judges = useMemo(() => [...new Set(cases.map(item => item.judge_status || 'not_received'))].sort(), [cases]);
  const setFilter = value => dispatch(actions.filterChanged(value));
  const completion = cases.length ? Math.round((counts.completed / cases.length) * 100) : 0;
  const judgeCoverage = cases.length ? Math.round((counts.reports / cases.length) * 100) : 0;


  if (!snapshot) return <section className="empty"><h2>{error ? 'Suite temporarily unavailable' : 'Loading Suite'}</h2><p>{error || 'All planned Cases will appear here.'}</p></section>;

  const sortOrder = field => table.field === field ? table.order : null;
  const columns = [
    { title: 'Agent', key: 'agent', sorter: true, sortOrder: sortOrder('agent'), width: 230,
      render: (_, item) => <Button type="link" onClick={event => { event.stopPropagation(); onAgentSelect(item.agent_id); }}>{item.agent_id}</Button> },
    { title: 'Case', key: 'caseNumber', sorter: true, sortOrder: sortOrder('caseNumber'), width: 110,
      render: (_, item) => <Button type="link" onClick={event => { event.stopPropagation(); onCaseSelect(item); }}>Case {item.case_index + 1}</Button> },
    { title: 'Execution', key: 'status', sorter: true, sortOrder: sortOrder('status'), width: 230,
      render: (_, item) => <CaseStatus item={item} /> },
    { title: 'Judge', key: 'judge', sorter: true, sortOrder: sortOrder('judge'), width: 150,
      render: (_, item) => <div className="suite-judge-cell"><JudgeBadge status={item.judge_status} />{(item.host_accepted === false || item.host_acceptance === 'rejected') && <Text type="danger">Rejected by host</Text>}</div> },
    { title: 'Attempts', key: 'attempts', sorter: true, sortOrder: sortOrder('attempts'), width: 120,
      render: (_, item) => <div className="suite-attempt-count"><strong>{item.attempts.length}</strong><Text type="secondary">{item.retry_count > 0 ? `${item.retry_count} retries` : 'executions'}</Text></div> },
    { title: 'Last activity', key: 'updated', sorter: true, sortOrder: sortOrder('updated'), width: 170,
      render: (_, item) => latestTimestamp(item) ? new Date(latestTimestamp(item)).toLocaleString() : <Text type="secondary">Not recorded</Text> },
  ];

  return <section className="suite-overview" aria-label="Suite overview">
    <div className="suite-heading"><div><Text className="suite-eyebrow">SUITE OVERVIEW</Text><Title level={2}>All Cases</Title>
      <Text type="secondary">{agents.length} Agents, {cases.length} Cases{snapshot.effective_workers != null ? `, ${snapshot.effective_workers} active workers` : ''}</Text></div>
      <Space className="suite-heading-actions" wrap><Text className={error ? 'suite-connection disconnected' : 'suite-connection'} role="status">{error ? 'Sync disconnected, showing retained data' : `Synced ${updated || 'connecting'}`}</Text><ExportReportButton /></Space></div>

    {error && <Alert type="warning" showIcon message="Live sync is temporarily unavailable" description="The latest saved Suite data remains visible. The viewer will retry automatically." />}

    <SuiteActivity cases={cases} jobs={snapshot.jobs || []} onCaseSelect={onCaseSelect} onAgentSelect={onAgentSelect} disconnected={Boolean(error)} />
    <div className="suite-visuals">
      <div className="suite-metrics" aria-label="Case statistics">
        <Metric value={counts.completed} label="Completed" tone="complete" />
        <Metric value={counts.running} label="Running" tone="active" />
        <Metric value={counts.retry_wait} label="Retry pending" tone="warning" />
        <Metric value={counts.attention} label="Needs attention" tone="danger" />
        <Metric value={counts.queued} label="Queued" />
      </div>
      <div className="suite-progress-panel" aria-label="Suite completion charts">
        <div><Progress type="dashboard" percent={completion} size={108} strokeColor="#2f6d51" /><span>Execution complete</span></div>
        <div><Progress type="dashboard" percent={judgeCoverage} size={108} strokeColor="#55796a" /><span>Judge coverage</span></div>
      </div>
    </div>

    <div className="suite-report-line"><span>Judge reports <strong>{counts.reports}/{cases.length}</strong></span><span>Host accepted <strong>{counts.accepted}</strong></span></div>
    <AgentSummaryCards cases={cases} jobs={snapshot.jobs || []} onSelect={onAgentSelect} />

    <div className="suite-table-heading"><div><Title level={3}>Cases</Title><Text type="secondary">Select a result to inspect the complete Case record.</Text></div>
      <Space><Text type="secondary">Showing {visible.length} of {cases.length}</Text><Segmented className="case-view-toggle" value={table.view} onChange={view => dispatch(actions.tableChanged({ view }))}
        options={[{ value: 'table', label: <Tooltip title="Table view"><TableOutlined aria-label="Table view" /></Tooltip> }, { value: 'grid', label: <Tooltip title="Card view"><AppstoreOutlined aria-label="Card view" /></Tooltip> }]} /></Space></div>
    <div className="suite-filters" aria-label="Filter Cases">
      <Input.Search allowClear value={filters.query} placeholder="Search Agent, Case ID, status, or error" onChange={event => setFilter({ query: event.target.value })} />
      <Select mode="multiple" maxTagCount="responsive" allowClear value={filters.agents} options={agents.map(value => ({ value, label: value }))} placeholder="All Agents" onChange={value => setFilter({ agents: value })} />
      <Select mode="multiple" maxTagCount="responsive" allowClear value={filters.statuses} options={statuses.map(value => ({ value, label: executionLabels[value] || value }))} placeholder="All execution states" onChange={value => setFilter({ statuses: value })} />
      <Select mode="multiple" maxTagCount="responsive" allowClear value={filters.judges} options={judges.map(value => ({ value, label: value === 'not_received' ? 'Judge not received' : value }))} placeholder="All Judge results" onChange={value => setFilter({ judges: value })} />
      <label className="suite-switch"><Switch size="small" checked={filters.attention} onChange={value => setFilter({ attention: value })} /><span>Needs attention</span></label>
      <label className="suite-switch"><Switch size="small" checked={filters.retried} onChange={value => setFilter({ retried: value })} /><span>Retried</span></label>
      <Button onClick={() => dispatch(actions.filtersReset())}>Reset</Button>
    </div>

    {table.view === 'grid' ? <CaseCardGrid cases={visible} page={table.page} pageSize={table.pageSize} onSelect={onCaseSelect}
      onPage={(page, pageSize) => dispatch(actions.tableChanged({ page: table.pageSize === pageSize ? page : 1, pageSize }))} /> : <Table className="suite-table" rowKey="key" columns={columns} dataSource={visible} size="middle" tableLayout="fixed" scroll={{ x: 1140 }}
      rowClassName={item => isActive(item.execution_status) ? 'suite-row-running' : ''}
      onRow={item => ({ onClick: () => onCaseSelect(item), onKeyDown: event => { if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); onCaseSelect(item); } }, tabIndex: 0 })}
      onChange={(pagination, _tableFilters, sorter) => dispatch(actions.tableChanged({ page: pagination.current, pageSize: pagination.pageSize,
        field: sorter.columnKey || table.field, order: sorter.order || table.order }))}
      pagination={{ current: table.page, pageSize: table.pageSize, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], showTotal: total => `${total} Cases` }}
      locale={{ emptyText: cases.length ? 'No Cases match the current filters.' : 'Waiting for the Suite test plan.' }} />}
  </section>;
}

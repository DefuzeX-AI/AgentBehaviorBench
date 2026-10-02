import {
  InsertRowLeftOutlined,
  MenuFoldOutlined,
  ReloadOutlined,
  SearchOutlined,
  SwitcherOutlined,
} from '@ant-design/icons';
import { Button, Input, Skeleton, Tooltip, Typography } from 'antd';
import { useState } from 'react';
import { suiteCatalogRows } from './suiteCatalog.js';
import SuiteNavEntry from './SuiteNavEntry.jsx';
import './navigation.css';

export default function SuiteSidebar({ snapshot, catalog, catalogError, overviewSelected = false, selectedCaseKey, revision, busy, error, onSuiteSelect, onCaseSelect, onRefresh }) {
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState('');
  const suiteId = snapshot?.suite_id || 'Loading Suite';
  const normalizedQuery = query.trim().toLowerCase();
  const rows = suiteCatalogRows(catalog, snapshot);

  if (collapsed) return <aside className="sidebar suite-sidebar suite-sidebar-collapsed" aria-label="Suite navigation">
    <div className="suite-collapsed-nav">
      <Tooltip title="Expand sidebar" placement="right"><Button type="text" icon={<InsertRowLeftOutlined />} onClick={() => setCollapsed(false)} aria-label="Expand sidebar" /></Tooltip>
      <Tooltip title="Benchmark overview" placement="right"><Button type="text" icon={<SwitcherOutlined />} href="/" aria-label="Benchmark overview" aria-current={overviewSelected ? 'page' : undefined} /></Tooltip>
      <i className="suite-collapsed-divider" />
      {!overviewSelected && <Tooltip title={suiteId} placement="right"><button type="button" className="suite-collapsed-suite selected" onClick={onSuiteSelect} aria-label={`Open ${suiteId}`}>S</button></Tooltip>}
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

    <a href="/" className={`suite-overview-link${overviewSelected ? ' selected' : ''}`} aria-current={overviewSelected ? 'page' : undefined}><SwitcherOutlined />Benchmark overview</a>
    <div className="suite-sidebar-search"><Input allowClear size="small" prefix={<SearchOutlined />} value={query}
      onChange={event => setQuery(event.target.value)} placeholder="Filter Suites, Agents or Cases" aria-label="Filter Suites, Agents or Cases" /></div>

    <div className="suite-sidebar-label"><Typography.Text type="secondary">SUITES ({rows.length})</Typography.Text></div>
    {error && <p role="alert" className="sidebar-error">{error}</p>}
    {catalogError && <p role="alert" className="sidebar-error">Suite list: {catalogError}</p>}
    {!!catalog?.warnings?.length && <details className="suite-catalog-warnings"><summary>{catalog.warnings.length} unavailable records</summary>
      {catalog.warnings.map(message => <p key={message}>{message}</p>)}</details>}
    {!snapshot && !catalog ? <Skeleton active paragraph={{ rows: 6 }} /> : <nav className="suite-nav" aria-label="Suite, Agent, and Case results">
      {rows.map(row => <SuiteNavEntry key={row.suite_id} row={row} selected={row.suite_id === suiteId}
        snapshot={row.suite_id === suiteId ? snapshot : null} selectedCaseKey={selectedCaseKey}
        query={normalizedQuery} revision={revision} onSuiteSelect={onSuiteSelect} onCaseSelect={onCaseSelect} />)}
    </nav>}
  </aside>;
}

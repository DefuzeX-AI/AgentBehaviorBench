import { Button, Skeleton, Tag, Tree, Typography } from 'antd';
import { countCases, executionLabels, normalizeCases } from '../suite/model.js';
import './navigation.css';

const judgeColor = status => status === 'pass' ? 'success'
  : status === 'issue' || status === 'insufficient_evidence' ? 'warning' : 'default';

function CaseTitle({ item }) {
  return <span className="suite-tree-case">
    <span><strong>Case {item.case_index + 1}</strong><small>{item.case_id || 'Pending Case ID'}</small></span>
    <Tag color={item.judge_status ? judgeColor(item.judge_status) : item.execution_status === 'completed' ? 'success' : 'processing'}>
      {item.judge_status || executionLabels[item.execution_status] || item.execution_status}
    </Tag>
  </span>;
}

export default function SuiteSidebar({ snapshot, selectedCaseKey, busy, error, onSuiteSelect, onCaseSelect, onRefresh }) {
  const cases = normalizeCases(snapshot);
  const counts = countCases(cases);
  const suiteId = snapshot?.suite_id || 'Loading Suite';
  const treeData = snapshot ? [{
    key: `suite:${suiteId}`,
    title: <span className="suite-tree-root"><strong>Suite</strong><small title={suiteId}>{suiteId}</small>
      <span>{counts.completed}/{cases.length} complete, {counts.reports}/{cases.length} judged</span></span>,
    children: (snapshot.jobs || []).map(job => ({
      key: `agent:${job.agent_id}`,
      selectable: false,
      title: <span className="suite-tree-agent"><strong>{job.agent_id}</strong><small>{(job.cases || []).length} Cases</small></span>,
      children: cases.filter(item => item.agent_id === job.agent_id).map(item => ({
        key: `case:${item.key}`,
        title: <CaseTitle item={item} />,
      })),
    })),
  }] : [];
  const selected = selectedCaseKey ? `case:${selectedCaseKey}` : snapshot ? `suite:${suiteId}` : undefined;
  function select(keys) {
    const key = keys[0];
    if (!key) return;
    if (key.startsWith('suite:')) onSuiteSelect();
    if (key.startsWith('case:')) {
      const item = cases.find(value => `case:${value.key}` === key);
      if (item) onCaseSelect(item);
    }
  }
  return <aside className="sidebar suite-sidebar" aria-label="Suite navigation">
    <div className="sidebar-heading"><div><Typography.Text type="secondary">RESULTS</Typography.Text><h2>Benchmarks</h2></div>
      <Button size="small" onClick={onRefresh} loading={busy}>Refresh</Button></div>
    {error && <p role="alert" className="sidebar-error">{error}</p>}
    {!snapshot ? <Skeleton active paragraph={{ rows: 6 }} /> : <Tree className="suite-tree" blockNode defaultExpandAll
      selectedKeys={selected ? [selected] : []} treeData={treeData} onSelect={select} />}
  </aside>;
}

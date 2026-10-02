import { useEffect, useState } from 'react';
import { Alert, Button, Input, Popover, Table, Tabs, Typography } from 'antd';
import { DownOutlined, DownloadOutlined, InfoCircleOutlined, RightOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons';
import SuiteSidebar from '../navigation/SuiteSidebar.jsx';
import EvaluationSourceBadge from '../suite/EvaluationSourceBadge.jsx';
import useLiveJson from '../useLiveJson.js';
import { caseVolume, evaluatorHref, evaluatorTabName, groundTruthProgress, selectedEvaluator } from './model.js';
import './benchmark.css';

const endpoint = '/api/benchmark/overview';
const { Text } = Typography;

function CountingRules() {
  return <dl className="benchmark-definitions">
    <dt>Benchmark score (proposed)</dt><dd>GT Discovery@B: 100 × the mean discovery fraction across a fixed set of Agents, averaged over independent trials at the same budget B. Agent/SDK versions, GT revisions and retry rules must be frozen before testing. No formal score is computed from unconstrained historical runs.</dd>
    <dt>Ground truth</dt><dd>Human-confirmed Agent defects, reproduced with the same Case across multiple rounds. Stored in each Agent’s ground_truth/manifest.json.</dd>
    <dt>Discovered</dt><dd>An explicit assessment confirms that a Case reproduced the defect and its Judge correctly identified it. Repeated discoveries count once per defect.</dd>
    <dt>Observed GT coverage</dt><dd>100 × discovered defects / known defects for Agents represented in the selected SDK’s Suites. Only that SDK’s assessments count. This is historical coverage; comparable benchmark scores require a shared, frozen Agent/GT set and equal budgets.</dd>
    <dt>Not assessed</dt><dd>No complete assessment for the current ground truth revision. A Judge’s “issue” verdict alone does not count as discovery.</dd>
    <dt>Cases</dt><dd>Includes planned and queued Cases. Each reuse adds a Case; retries stay within the same Case. Execution completion is separate from discovery.</dd>
  </dl>;
}

function BenchmarkTotals({ totals, groundTruth }) {
  const progress = groundTruthProgress(groundTruth);
  return <section className="benchmark-summary" aria-label="Ground truth results">
    <div className="benchmark-total"><span>Benchmark score</span><strong aria-label="Benchmark score unavailable">—</strong>
      <small>Protocol not configured</small></div>
    <div className={`benchmark-discovery${progress.percent === null ? ' unassessed' : ''}`}>
      <div className="benchmark-discovery-heading"><strong>{progress.found} <span>Discovered</span></strong><b>{progress.label}</b></div>
      <div className="benchmark-discovery-track" role="img" aria-label={progress.description}>
        <span style={{ width: `${progress.percent || 0}%` }} />
      </div>
      <span className="benchmark-assessment-state">Observed GT coverage · {progress.detail}</span>
      <small className="benchmark-configuration-state">{groundTruth?.configured_agent_count || 0}/{totals.agent_count} Agents have ground truth</small>
    </div>
    <dl className="benchmark-scope"><div><dt>Known defects</dt><dd>{progress.known}</dd></div>
      <div><dt>Cases</dt><dd>{totals.case_count.toLocaleString()}</dd></div>
      <div><dt>Suites</dt><dd>{totals.suite_count.toLocaleString()}</dd></div>
      <div><dt>Agents</dt><dd>{totals.agent_count.toLocaleString()}</dd></div></dl>
  </section>;
}

function AgentVolume({ agent, maximum }) {
  return <div className="benchmark-volume" role="img" aria-label={`${agent.case_count} ${agent.case_count === 1 ? 'Case' : 'Cases'}`}>
    <div className="benchmark-volume-space"><div className="benchmark-volume-bar" style={{ width: `${maximum ? agent.case_count / maximum * 100 : 0}%` }} /></div>
    <strong>{agent.case_count.toLocaleString()}</strong>
  </div>;
}

function Discovery({ value }) {
  const progress = groundTruthProgress(value);
  return <span className={`benchmark-agent-discovery${progress.percent === null ? ' unassessed' : ''}`}>
    <strong>{progress.found}{progress.percent !== null && <small> / {value.defect_count}</small>}</strong>{progress.percent !== null && <small>{progress.label}</small>}
  </span>;
}

function AssessmentValue({ value }) {
  return <span className={value === true ? 'benchmark-confirmed' : 'benchmark-muted'}>{value === true ? 'Yes' : value === false ? 'No' : 'Not assessed'}</span>;
}

function AgentDetails({ agent }) {
  const defects = agent.ground_truth?.defects || [];
  return <div className="benchmark-details">
    {!!defects.length && <><h3>Ground truth</h3><Table className="benchmark-breakdown" rowKey="id" size="small" pagination={false}
      dataSource={defects} scroll={{ x: 620 }} columns={[
        { title: 'Known defect', dataIndex: 'title', render: (title, defect) => <div className="benchmark-agent"><strong>{title}</strong><Text type="secondary">{defect.id}</Text></div> },
        { title: 'Case reproduced', dataIndex: 'case_reproduced', width: 145, render: value => <AssessmentValue value={value} /> },
        { title: 'Judge detected', dataIndex: 'judge_detected', width: 145, render: value => <AssessmentValue value={value} /> },
      ]} /></>}
    <h3>Suites</h3><Table className="benchmark-breakdown" rowKey="suite_id" size="small" pagination={false}
      dataSource={agent.suites} scroll={{ x: 620 }} locale={{ emptyText: 'No saved Suites for this Agent.' }}
      columns={[
        { title: 'Suite', key: 'suite', render: (_, suite) => <div>
          <a href={`${suite.url}#agent=${encodeURIComponent(agent.agent_id)}&tab=overview`}>{suite.suite_id}</a>
          {suite.origin_suite_id && <Text type="secondary" className="benchmark-reused">Reuse</Text>}
        </div> },
        { title: 'Evaluator', key: 'evaluator', width: 140, render: (_, suite) => <EvaluationSourceBadge source={suite.evaluation_source} compact /> },
        { title: 'Cases', dataIndex: 'case_count', align: 'right', width: 90 },
        { title: 'Execution completed', dataIndex: 'completed_case_count', align: 'right', width: 155 },
      ]} />
  </div>;
}

export default function BenchmarkOverview({ catalogEndpoint }) {
  const [revision, setRevision] = useState(0);
  const [requestedSdk, setRequestedSdk] = useState(() => new URLSearchParams(window.location.search).get('sdk'));
  const overview = useLiveJson(endpoint, revision);
  const catalog = useLiveJson(catalogEndpoint, revision);
  const data = overview.data;
  const evaluators = data?.evaluators || [];
  const active = selectedEvaluator(evaluators, requestedSdk);

  useEffect(() => {
    const sync = () => setRequestedSdk(new URLSearchParams(window.location.search).get('sdk'));
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);

  useEffect(() => {
    if (!active || active.id === requestedSdk) return;
    window.history.replaceState(null, '', evaluatorHref(active.id, window.location));
    setRequestedSdk(active.id);
  }, [active?.id, requestedSdk]);

  function selectSdk(id) {
    window.history.pushState(null, '', evaluatorHref(id, window.location));
    setRequestedSdk(id);
  }

  function exportSelected() {
    if (!active) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(active, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `benchmark-${active.id.replace(/[^a-zA-Z0-9_.-]/g, '_')}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <div className="workspace suite-workspace">
    <SuiteSidebar catalog={catalog.data} catalogError={catalog.error} overviewSelected revision={revision}
      busy={!data && !overview.error} onRefresh={() => setRevision(value => value + 1)} />
    <main className="suite-main benchmark-main">
      <header className="benchmark-header"><h1>Benchmark overview</h1>
        <div className="benchmark-header-actions">
          <span className={`benchmark-sync${overview.error ? ' disconnected' : ''}`} role="status"><i />{overview.error ? 'Offline' : overview.updated ? 'Live' : 'Connecting'}</span>
          <Popover trigger="click" placement="bottomRight" title="Benchmark metrics" content={<CountingRules />}>
            <Button type="text" icon={<InfoCircleOutlined />} aria-label="How benchmark metrics are counted" /></Popover>
          <Button icon={<DownloadOutlined />} onClick={exportSelected} disabled={!active}>Export JSON</Button>
        </div></header>
      <section className="benchmark-overview" aria-label="Benchmark overview">
        {overview.error && <Alert type="warning" showIcon message="Overview sync is temporarily unavailable"
          description={data ? 'Showing the last received totals. The viewer will retry automatically.' : overview.error} />}
        {!data ? <section className="empty" role="status"><h3>{overview.error ? 'Overview unavailable' : 'Collecting benchmark results…'}</h3></section>
          : !evaluators.length ? <section className="empty" role="status"><h3>{Array.isArray(data.evaluators) ? 'No saved SDK runs yet' : 'SDK overview unavailable'}</h3>
            <p>{Array.isArray(data.evaluators) ? 'Run a Suite to see its SDK results here.' : 'Restart the viewer to load SDK results.'}</p></section>
          : <Tabs className="benchmark-sdk-tabs" aria-label="Evaluation SDK" activeKey={active?.id} onChange={selectSdk} destroyOnHidden
            items={evaluators.map(evaluator => ({ key: evaluator.id,
              label: <span className="benchmark-sdk-label"><strong>{evaluatorTabName(evaluator)}</strong><small>{evaluator.totals.suite_count} {evaluator.totals.suite_count === 1 ? 'Suite' : 'Suites'}</small></span>,
              children: <EvaluatorResults key={evaluator.id} data={evaluator} catalogWarnings={data.warnings || []} />,
            }))} />}
      </section>
    </main>
  </div>;
}

function EvaluatorResults({ data, catalogWarnings }) {
  const [query, setQuery] = useState('');
  const rows = data.agents.filter(agent => agent.agent_id.toLowerCase().includes(query.trim().toLowerCase()));
  const maximum = Math.max(0, ...data.agents.map(agent => agent.case_count));
  const diagnostics = [...new Set([...catalogWarnings, ...(data.warnings || []), ...(data.ground_truth?.warnings || [])])];
  return <section className="benchmark-sdk-results" aria-label={`${evaluatorTabName(data)} results`}>
          {data.id.startsWith('@') && <Alert type="warning" showIcon title="SDK attribution is incomplete"
            description="These Suites are kept separate from named SDK results because their evaluator records are missing, partial or mixed." />}
          <BenchmarkTotals totals={data.totals} groundTruth={data.ground_truth} />
          {!!diagnostics.length && <div className="benchmark-data-note"><Popover trigger="click" placement="bottomLeft" title="Data notices"
            content={<ul className="benchmark-excluded">{diagnostics.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}>
            <Button type="text" size="small" icon={<WarningOutlined />}>{diagnostics.length} data notices</Button>
          </Popover></div>}
          <div className="benchmark-table-heading"><h2>Agents <span>{data.agents.length}</span></h2>
            <Input allowClear prefix={<SearchOutlined />} placeholder="Filter Agents" aria-label="Filter overview Agents"
              value={query} onChange={event => setQuery(event.target.value)} /></div>
          <Table className="benchmark-table" rowKey="agent_id" dataSource={rows} size="middle" scroll={{ x: 740 }}
            columns={[
              { title: 'Agent', dataIndex: 'agent_id', sorter: (a, b) => a.agent_id.localeCompare(b.agent_id),
                render: (id, agent) => <div className="benchmark-agent"><strong>{id}</strong><Text type="secondary">{caseVolume(agent)}</Text></div> },
              { title: 'Ground truth', key: 'ground_truth', width: 145, sorter: (a, b) => (a.ground_truth?.defect_count || 0) - (b.ground_truth?.defect_count || 0),
                render: (_, agent) => { const progress = groundTruthProgress(agent.ground_truth); return <div className="benchmark-agent-ground-truth"><strong>{progress.known}</strong><small>{agent.ground_truth?.defect_count > 0 ? `${agent.ground_truth.assessed_defect_count}/${agent.ground_truth.defect_count} assessed` : progress.state}</small></div>; } },
              { title: 'Discovered', key: 'discovered', align: 'right', width: 115, sorter: (a, b) => (a.ground_truth?.discovered_defect_count || 0) - (b.ground_truth?.discovered_defect_count || 0),
                render: (_, agent) => <Discovery value={agent.ground_truth} /> },
              { title: 'Cases', dataIndex: 'case_count', width: '24%', sorter: (a, b) => a.case_count - b.case_count,
                render: (_, agent) => <AgentVolume agent={agent} maximum={maximum} /> },
            ]}
            expandable={{ expandedRowRender: agent => <AgentDetails agent={agent} />, columnWidth: 38,
              columnTitle: <span className="sr-only">Agent details</span>,
              expandIcon: ({ expanded, onExpand, record }) => <Button type="text" size="small" icon={expanded ? <DownOutlined /> : <RightOutlined />}
                aria-label={`${expanded ? 'Hide' : 'Show'} details for ${record.agent_id}`} aria-expanded={expanded} onClick={event => onExpand(record, event)} /> }}
            pagination={{ defaultPageSize: 20, hideOnSinglePage: true, showSizeChanger: true }}
            locale={{ emptyText: data.agents.length ? 'No Agents match your filter.' : 'No saved Suites or ground truth available yet.' }} />
      </section>;
}

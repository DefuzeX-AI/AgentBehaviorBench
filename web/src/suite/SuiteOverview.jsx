import { Fragment, useMemo } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { actions } from './store.js';
import { countCases, executionLabels, needsAttention, normalizeCases } from './model.js';
import CaseStatus, { JudgeBadge } from './CaseStatus.jsx';
import AttemptDetails from './AttemptDetails.jsx';
import SuiteControls, { RetryButton } from './SuiteControls.jsx';
import './suite.css';

export default function SuiteOverview() {
  const dispatch = useDispatch();
  const { snapshot, error, updated, expanded, filters } = useSelector(state => state.suite);
  const cases = useMemo(() => normalizeCases(snapshot), [snapshot]);
  const counts = useMemo(() => countCases(cases), [cases]);
  const agents = [...new Set(cases.map(item => item.agent_id))];
  const visible = cases.filter(item => (!filters.agent || item.agent_id === filters.agent)
    && (!filters.status || item.execution_status === filters.status)
    && (!filters.attention || needsAttention(item.execution_status)));
  const setFilter = value => dispatch(actions.filterChanged(value));
  if (!snapshot) return <section className="empty"><h2>{error ? 'Suite temporarily unavailable' : 'Loading Suite'}</h2><p>{error || 'All planned Cases will appear here.'}</p></section>;
  return <section className="suite-overview" aria-label="Suite Case overview">
    <div className="suite-heading"><div><h2>All Cases</h2><p>{agents.length} Agents · {cases.length} Cases{snapshot.effective_workers != null ? ` · concurrency ${snapshot.effective_workers}` : ''}</p></div>
      <span className={`suite-connection ${error ? 'disconnected' : ''}`} role="status">{error ? 'Sync disconnected · showing last data' : `Synced ${updated || 'connecting'}`}</span></div>
    <div className="suite-metrics" aria-label="Case statistics">
      {[[counts.completed, 'Completed'], [counts.running, 'Running'], [counts.retry_wait, 'Retry pending'], [counts.attention, 'Needs attention'], [counts.queued, 'Queued / pending generation']].map(([value, label]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}
    </div>
    <p className="suite-report-count">Judge reports: <strong>{counts.reports} / {cases.length}</strong> · host-accepted: {counts.accepted}. An issue verdict reports a behavioral finding, not an execution failure.</p>
    <SuiteControls cases={cases} />
    <div className="suite-filters" aria-label="Filter Cases">
      <label><span className="sr-only">Filter Agent</span><select value={filters.agent} onChange={event => setFilter({ agent: event.target.value })}><option value="">All Agents</option>{agents.map(agent => <option key={agent}>{agent}</option>)}</select></label>
      <label><span className="sr-only">Filter execution status</span><select value={filters.status} onChange={event => setFilter({ status: event.target.value })}><option value="">All execution states</option>{[...new Set(cases.map(item => item.execution_status))].map(status => <option key={status} value={status}>{executionLabels[status] || status}</option>)}</select></label>
      <label className="suite-checkbox"><input type="checkbox" checked={filters.attention} onChange={event => setFilter({ attention: event.target.checked })} />Needs attention only</label>
      <span className="suite-muted">Showing {visible.length} of {cases.length} Cases</span>
    </div>
    <div className="suite-table-wrap"><table className="suite-table"><thead><tr><th>Agent / Case</th><th>Execution status</th><th>Judge</th><th>Attempts</th><th>Actions</th></tr></thead><tbody>
      {visible.map(item => <Fragment key={item.key}>
        <tr className={expanded[item.key] ? 'suite-row-expanded' : ''}>
          <th scope="row"><strong>{item.agent_id}</strong><span>Case {item.case_index + 1}</span>{item.case_id && <small title={item.case_id}>{item.case_id}</small>}</th>
          <td><CaseStatus item={item} /></td><td><JudgeBadge status={item.judge_status} />{(item.host_accepted === false || item.host_acceptance === 'rejected') && <small className="suite-error-text">Rejected by host</small>}</td>
          <td>{item.attempts.length}<small>{item.retry_count > 0 ? `${item.retry_count} retries` : 'executions'}</small></td>
          <td><div className="suite-row-actions"><button aria-expanded={Boolean(expanded[item.key])} aria-label={`${expanded[item.key] ? 'Collapse' : 'View'} ${item.agent_id} Case ${item.case_index + 1}`} onClick={() => dispatch(actions.caseToggled(item))}>{expanded[item.key] ? 'Collapse' : 'View'}</button><RetryButton item={item} /></div></td>
        </tr>
        {expanded[item.key] && <tr className="suite-detail-row"><td colSpan={5}><AttemptDetails item={item} /></td></tr>}
      </Fragment>)}
      {!visible.length && <tr><td colSpan={5} className="suite-no-cases">{cases.length ? 'No Cases match the current filters.' : 'Waiting for the Suite test plan.'}</td></tr>}
    </tbody></table></div>
  </section>;
}

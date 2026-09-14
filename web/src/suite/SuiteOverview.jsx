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
  if (!snapshot) return <section className="empty"><h2>{error ? '暂时无法连接 Suite' : '正在加载 Suite'}</h2><p>{error || '计划中的全部 Case 将在这里显示。'}</p></section>;
  return <section className="suite-overview" aria-label="Suite 多 Case 总览">
    <div className="suite-heading"><div><h2>全部 Case</h2><p>{agents.length} 个 Agent · {cases.length} 个 Case{snapshot.effective_workers != null ? ` · 并发 ${snapshot.effective_workers}` : ''}</p></div>
      <span className={`suite-connection ${error ? 'disconnected' : ''}`} role="status">{error ? '同步断开 · 保留上次数据' : `同步于 ${updated || '连接中'}`}</span></div>
    <div className="suite-metrics" aria-label="Case 统计">
      {[[counts.completed, '已完成'], [counts.running, '运行中'], [counts.retry_wait, '等待重试'], [counts.attention, '需处理'], [counts.queued, '排队 / 待生成']].map(([value, label]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}
    </div>
    <p className="suite-report-count">Judge 报告：<strong>{counts.reports} / {cases.length}</strong> · 已确认宿主验收：{counts.accepted}。判决 issue 表示发现行为问题，不等于执行出错。</p>
    <SuiteControls cases={cases} />
    <div className="suite-filters" aria-label="筛选 Case">
      <label><span className="sr-only">筛选 Agent</span><select value={filters.agent} onChange={event => setFilter({ agent: event.target.value })}><option value="">全部 Agent</option>{agents.map(agent => <option key={agent}>{agent}</option>)}</select></label>
      <label><span className="sr-only">筛选执行状态</span><select value={filters.status} onChange={event => setFilter({ status: event.target.value })}><option value="">全部执行状态</option>{[...new Set(cases.map(item => item.execution_status))].map(status => <option key={status} value={status}>{executionLabels[status] || status}</option>)}</select></label>
      <label className="suite-checkbox"><input type="checkbox" checked={filters.attention} onChange={event => setFilter({ attention: event.target.checked })} />仅看需处理</label>
      <span className="suite-muted">显示 {visible.length} / {cases.length} 个 Case</span>
    </div>
    <div className="suite-table-wrap"><table className="suite-table"><thead><tr><th>Agent / Case</th><th>执行状态</th><th>Judge</th><th>尝试</th><th>操作</th></tr></thead><tbody>
      {visible.map(item => <Fragment key={item.key}>
        <tr className={expanded[item.key] ? 'suite-row-expanded' : ''}>
          <th scope="row"><strong>{item.agent_id}</strong><span>Case {item.case_index + 1}</span>{item.case_id && <small title={item.case_id}>{item.case_id}</small>}</th>
          <td><CaseStatus item={item} /></td><td><JudgeBadge status={item.judge_status} />{(item.host_accepted === false || item.host_acceptance === 'rejected') && <small className="suite-error-text">宿主未验收</small>}</td>
          <td>{item.attempts.length}<small>{item.retry_count > 0 ? `重试 ${item.retry_count} 次` : '次执行'}</small></td>
          <td><div className="suite-row-actions"><button aria-expanded={Boolean(expanded[item.key])} aria-label={`${expanded[item.key] ? '收起' : '查看'} ${item.agent_id} Case ${item.case_index + 1}`} onClick={() => dispatch(actions.caseToggled(item))}>{expanded[item.key] ? '收起' : '查看'}</button><RetryButton item={item} /></div></td>
        </tr>
        {expanded[item.key] && <tr className="suite-detail-row"><td colSpan={5}><AttemptDetails item={item} /></td></tr>}
      </Fragment>)}
      {!visible.length && <tr><td colSpan={5} className="suite-no-cases">{cases.length ? '没有符合当前筛选的 Case。' : '等待 Suite 登记测试计划。'}</td></tr>}
    </tbody></table></div>
  </section>;
}

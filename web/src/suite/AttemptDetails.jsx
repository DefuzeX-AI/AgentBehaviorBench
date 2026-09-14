import { lazy, Suspense, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { actions } from './store.js';
import { currentAttempt, errorText, executionStatus, reportOf } from './model.js';
import { ExecutionBadge, JudgeBadge } from './CaseStatus.jsx';
import EvaluationView from '../evaluation/EvaluationView.jsx';
import TraceView from '../otel/TraceView.jsx';

const RawRunView = lazy(() => import('../RawRunView.jsx'));

export default function AttemptDetails({ item }) {
  const dispatch = useDispatch();
  const selectedId = useSelector(state => state.suite.selectedAttempts[item.key]);
  const [view, setView] = useState('evaluation');
  const attempt = selectedId ? item.attempts.find(value => value.attempt_id === selectedId) : currentAttempt(item);
  const artifact = attempt?.artifact_run_id;
  const rejected = attempt?.host_accepted === false || attempt?.host_acceptance === false || attempt?.host_acceptance === 'rejected';
  return <section className="suite-attempt" aria-label={`${item.agent_id} Case ${item.case_index + 1} 详情`}>
    <div className="suite-attempt-heading">
      <label>执行记录 <select value={attempt?.attempt_id || ''} onChange={event => dispatch(actions.attemptSelected({ key: item.key, attempt_id: event.target.value }))}>
        {!item.attempts.length && <option value="">尚未开始执行</option>}
        {item.attempts.map(value => <option key={value.attempt_id} value={value.attempt_id}>第 {value.attempt_number} 次执行{value.attempt_id === item.active_attempt_id ? ' · 当前' : ''}</option>)}
      </select></label>
      {attempt && <span><ExecutionBadge status={executionStatus(attempt)} /> <JudgeBadge status={attempt.judge_status || reportOf(attempt)?.status} /></span>}
    </div>
    <p className="suite-identity">Case ID：<code>{item.case_id || '尚未生成'}</code>{artifact && <> · Run：<code>{artifact}</code></>}</p>
    {attempt?.error && <p className="suite-notice" role="status">{errorText(attempt.error)}</p>}
    {rejected && <p className="suite-notice" role="status">宿主未接受这次执行。已收到的 Judge 报告仍保留，不计为已验收结果。</p>}
    {artifact ? <>
      <nav className="trace-tabs" aria-label={`${item.agent_id} Case ${item.case_index + 1} 详情视图`}>
        {[['evaluation', 'Case / SDK / Judge'], ['otel', 'OTel 调用树'], ['raw', '交互时间线']].map(([value, label]) => <button key={value} aria-pressed={view === value} onClick={() => setView(value)}>{label}</button>)}
      </nav>
      {view === 'evaluation' ? <EvaluationView key={artifact} run={artifact} /> : view === 'otel' ? <TraceView key={artifact} run={artifact} /> :
        <Suspense fallback={<p>正在加载交互记录…</p>}><RawRunView key={artifact} run={artifact} /></Suspense>}
    </> : <>
      <p className="suite-muted">{attempt ? '这次执行尚未登记可查看的产物目录。' : 'Case 尚未开始执行，生成与恢复进度会在总览同步。'}</p>
      {item.result && <details><summary>查看已保存结果</summary><pre>{JSON.stringify(item.result, null, 2)}</pre></details>}
    </>}
  </section>;
}

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
  return <section className="suite-attempt" aria-label={`${item.agent_id} Case ${item.case_index + 1} details`}>
    <div className="suite-attempt-heading">
      <label>Execution attempt <select value={attempt?.attempt_id || ''} onChange={event => dispatch(actions.attemptSelected({ key: item.key, attempt_id: event.target.value }))}>
        {!item.attempts.length && <option value="">Execution has not started</option>}
        {item.attempts.map(value => <option key={value.attempt_id} value={value.attempt_id}>Attempt {value.attempt_number}{value.attempt_id === item.active_attempt_id ? ' · current' : ''}</option>)}
      </select></label>
      {attempt && <span><ExecutionBadge status={executionStatus(attempt)} /> <JudgeBadge status={attempt.judge_status || reportOf(attempt)?.status} /></span>}
    </div>
    <p className="suite-identity">Case ID: <code>{item.case_id || 'not generated'}</code>{artifact && <> · Run: <code>{artifact}</code></>}</p>
    {attempt?.error && <p className="suite-notice" role="status">{errorText(attempt.error)}</p>}
    {rejected && <p className="suite-notice" role="status">The host rejected this execution. Its Judge report is retained but does not count as an accepted result.</p>}
    {artifact ? <>
      <nav className="trace-tabs" aria-label={`${item.agent_id} Case ${item.case_index + 1} detail views`}>
        {[['evaluation', 'Case / SDK / Judge'], ['otel', 'OTel call tree'], ['raw', 'Interaction timeline']].map(([value, label]) => <button key={value} aria-pressed={view === value} onClick={() => setView(value)}>{label}</button>)}
      </nav>
      {view === 'evaluation' ? <EvaluationView key={artifact} run={artifact} /> : view === 'otel' ? <TraceView key={artifact} run={artifact} /> :
        <Suspense fallback={<p>Loading interactions…</p>}><RawRunView key={artifact} run={artifact} /></Suspense>}
    </> : <>
      <p className="suite-muted">{attempt ? 'This attempt does not yet have a viewable artifact directory.' : 'Case execution has not started; generation and recovery progress will appear in the overview.'}</p>
      {item.result && <details><summary>View saved result</summary><pre>{JSON.stringify(item.result, null, 2)}</pre></details>}
    </>}
  </section>;
}

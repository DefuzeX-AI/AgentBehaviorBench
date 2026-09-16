import { executionLabels, executionStatus, jobProgress } from './suite/model.js';
const statuses = { ...executionLabels, degraded: 'Incomplete observation', unavailable: 'Unreadable record' };
const phases = { sdk_check: 'Check SDK', agent_start: 'Start Agent', case_generation: 'Generate Case', generate: 'Generate Case', execute: 'Execute Case / Judge', benchmark_execution: 'Execute Case / Judge', completed: 'Execution complete' };

export default function RunSidebar({ runs, jobs = [], selected, busy, error, onSelect, onRefresh }) {
  return <aside className="sidebar" aria-label="Run records">
    <div className="sidebar-heading"><h2>Run records</h2><button onClick={onRefresh} disabled={busy}>Refresh</button></div>
    <p className="sidebar-note">Local run records</p>
    {busy && <p role="status">Loading jobs…</p>}
    {error && <p role="alert" className="sidebar-error">{error}</p>}
    {!!jobs.length && <section aria-label="Agent job progress">
      <p className="sidebar-note">Agent jobs</p>
      {jobs.map(job => <div className="run-item" key={job.job_id || job.agent_id}>
        <strong>{job.agent_id}</strong>
        <span>{jobProgress(job)}</span>
        <span>{job.cases?.length || 0} Cases total</span>
        {(job.cases || []).map(caseItem => {
          const attempt = caseItem.attempts?.find(item => item.attempt_id === caseItem.active_attempt_id) || caseItem.attempts?.at(-1);
          const artifactId = attempt?.artifact_run_id || caseItem.artifact_run_id;
          return <div key={caseItem.job_id || caseItem.case_index} className="case-item">
            <span>Case {caseItem.case_index + 1} · {statuses[executionStatus(caseItem)] || executionStatus(caseItem)}</span>
            {caseItem.judge_status && <span>Judge：{caseItem.judge_status}</span>}
            {caseItem.case_id && <span title={caseItem.case_id}>{caseItem.case_id}</span>}
            {caseItem.status === 'running' && caseItem.stage && <span>{phases[caseItem.stage] || caseItem.stage}</span>}
            {artifactId && <button onClick={() => onSelect(artifactId)} aria-current={selected === artifactId ? 'true' : undefined}>View Case record</button>}
          </div>;
        })}
      </div>)}
    </section>}
    {!busy && !error && !runs.length && <p className="sidebar-note">Waiting for Case run records. Evidence directories appear automatically; inputs and verdicts are available in Suite progress.</p>}
    {!!runs.length && !!jobs.length && <p className="sidebar-note">Case run records</p>}
    <nav aria-label="Select run">{runs.map(run => <button key={run.id} className="run-item"
      aria-current={selected === run.id ? 'true' : undefined} onClick={() => onSelect(run.id)}>
      <strong>{run.agent}</strong><span title={run.id}>Run {run.id.slice(0, 8)}</span>
      {run.case_index != null && <span>Case {run.case_index + 1}{run.case_id ? ` · ${run.case_id}` : ''}</span>}
      <span>{statuses[run.status] || run.status}</span>
      <span>Updated: {run.updated ? new Date(run.updated).toLocaleString('en-US') : 'unknown time'}</span>
    </button>)}</nav>
  </aside>;
}

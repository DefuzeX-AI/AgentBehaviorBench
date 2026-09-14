const statuses = { queued: '排队中', cancelled: '已取消', skipped: '已跳过', succeeded: '已完成', failed: '失败', running: '运行中', degraded: '观测不完整', unavailable: '记录不可读' };
const phases = { sdk_check: '检查 SDK', agent_start: '启动 Agent', case_generation: '生成 Case', generate: '生成 Case', execute: '执行 Case / Judge', benchmark_execution: '执行 Case / Judge', completed: '执行结束' };

export default function RunSidebar({ runs, jobs = [], selected, busy, error, onSelect, onRefresh }) {
  return <aside className="sidebar" aria-label="运行记录">
    <div className="sidebar-heading"><h2>运行记录</h2><button onClick={onRefresh} disabled={busy}>刷新</button></div>
    <p className="sidebar-note">本地运行记录</p>
    {busy && <p role="status">正在读取任务…</p>}
    {error && <p role="alert" className="sidebar-error">{error}</p>}
    {!!jobs.length && <section aria-label="Agent 任务进度">
      <p className="sidebar-note">Agent 任务</p>
      {jobs.map(job => <div className="run-item" key={job.job_id || job.agent_id}>
        <strong>{job.agent_id}</strong><span>{statuses[job.status] || job.status}</span>
        {job.generation_status === 'running' && <span>正在生成 Case</span>}
        <span>运行 {job.counts?.running || 0} · 排队 {job.counts?.queued || 0} · 通过 {job.counts?.succeeded || 0} · 失败 {job.counts?.failed || 0}</span>
        {(job.cases || []).map(caseItem => {
          const run = runs.find(item => item.agent === job.agent_id && item.case_index === caseItem.case_index);
          return <div key={caseItem.job_id || caseItem.case_index} className="case-item">
            <span>Case {caseItem.case_index + 1} · {statuses[caseItem.status] || caseItem.status}</span>
            {caseItem.case_id && <span title={caseItem.case_id}>{caseItem.case_id}</span>}
            {caseItem.status === 'running' && caseItem.stage && <span>{phases[caseItem.stage] || caseItem.stage}</span>}
            {run && <button onClick={() => onSelect(run.id)} aria-current={selected === run.id ? 'true' : undefined}>查看 Case 记录</button>}
          </div>;
        })}
      </div>)}
    </section>}
    {!busy && !error && !runs.length && <p className="sidebar-note">等待 Case 运行记录。产生证据目录后会自动显示；输入和判决可在 Suite 进度查看。</p>}
    {!!runs.length && !!jobs.length && <p className="sidebar-note">Case 运行记录</p>}
    <nav aria-label="选择任务">{runs.map(run => <button key={run.id} className="run-item"
      aria-current={selected === run.id ? 'true' : undefined} onClick={() => onSelect(run.id)}>
      <strong>{run.agent}</strong><span title={run.id}>Run {run.id.slice(0, 8)}</span>
      {run.case_index != null && <span>Case {run.case_index + 1}{run.case_id ? ` · ${run.case_id}` : ''}</span>}
      <span>{statuses[run.status] || run.status}</span>
      <span>更新：{run.updated ? new Date(run.updated).toLocaleString('zh-CN') : '时间未知'}</span>
    </button>)}</nav>
  </aside>;
}

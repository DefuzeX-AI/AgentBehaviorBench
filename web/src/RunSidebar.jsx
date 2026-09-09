const statuses = { succeeded: '已完成', failed: '失败', running: '运行中', degraded: '观测不完整', unavailable: '记录不可读' };

export default function RunSidebar({ runs, selected, busy, error, onSelect, onRefresh }) {
  return <aside className="sidebar" aria-label="运行记录">
    <div className="sidebar-heading"><h2>运行记录</h2><button onClick={onRefresh} disabled={busy}>刷新</button></div>
    <p className="sidebar-note">本地 observe 记录</p>
    {busy && <p role="status">正在读取任务…</p>}
    {error && <p role="alert" className="sidebar-error">{error}</p>}
    {!busy && !error && !runs.length && <p className="sidebar-note">暂无任务。运行 observe 后点击刷新。</p>}
    <nav aria-label="选择任务">{runs.map(run => <button key={run.id} className="run-item"
      aria-current={selected === run.id ? 'true' : undefined} onClick={() => onSelect(run.id)}>
      <strong>{run.agent}</strong><span title={run.id}>Run {run.id.slice(0, 8)}</span>
      <span>{statuses[run.status] || run.status}</span>
      <span>更新：{run.updated ? new Date(run.updated).toLocaleString('zh-CN') : '时间未知'}</span>
    </button>)}</nav>
  </aside>;
}

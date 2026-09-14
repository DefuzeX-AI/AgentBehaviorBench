import { useEffect, useState } from 'react';
import { errorText, executionLabels, isComplete, needsAttention, phaseLabels } from './model.js';

export function ExecutionBadge({ status }) {
  const tone = isComplete(status) ? 'complete' : status === 'retry_wait' ? 'waiting' : needsAttention(status) ? 'attention' : 'active';
  return <span className={`suite-badge suite-badge-${tone}`}>{executionLabels[status] || status}</span>;
}

export function JudgeBadge({ status }) {
  if (!status) return <span className="suite-muted">尚未获得</span>;
  return <span className={`suite-badge suite-badge-${status === 'pass' ? 'complete' : status === 'issue' || status === 'insufficient_evidence' ? 'waiting' : 'active'}`}>{status}</span>;
}

function RetryTime({ at }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const time = typeof at === 'number' ? (at < 1e12 ? at * 1000 : at) : Date.parse(at);
  if (!Number.isFinite(time)) return <small>已安排重试，等待调度</small>;
  const seconds = Math.max(0, Math.ceil((time - now) / 1000));
  return <small>{seconds > 0 ? `${seconds} 秒后重试` : '重试时间已到，等待调度'}</small>;
}

export default function CaseStatus({ item }) {
  return <div className="suite-case-state">
    <ExecutionBadge status={item.execution_status} />
    {item.execution_status === 'retry_wait' && <RetryTime at={item.retry_at} />}
    {(item.phase || item.stage) && <small>{phaseLabels[item.stage] || phaseLabels[item.phase] || item.stage || item.phase}</small>}
    {item.current_step != null && <small>第 {item.current_step} 轮{item.total_steps != null ? ` / 共 ${item.total_steps} 轮` : ''}</small>}
    {(item.error || item.result?.error) && <small className="suite-error-text">{errorText(item.error || item.result?.error)}</small>}
    {item.recovery_reason && <small>{item.recovery_reason}</small>}
  </div>;
}

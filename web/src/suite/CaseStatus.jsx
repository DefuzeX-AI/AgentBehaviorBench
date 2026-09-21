import { useEffect, useState } from 'react';
import { Tag } from 'antd';
import { errorText, executionLabels, isComplete, needsAttention, phaseLabels } from './model.js';

export function ExecutionBadge({ status }) {
  const color = isComplete(status) ? 'success' : status === 'retry_wait' ? 'warning' : needsAttention(status) ? 'error' : 'processing';
  return <Tag color={color}>{executionLabels[status] || status}</Tag>;
}

export function JudgeBadge({ status }) {
  if (!status) return <Tag>Not received</Tag>;
  const color = status === 'pass' ? 'success' : status === 'issue' || status === 'insufficient_evidence' ? 'warning' : 'processing';
  return <Tag color={color}>{status}</Tag>;
}

function RetryTime({ at }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const time = typeof at === 'number' ? (at < 1e12 ? at * 1000 : at) : Date.parse(at);
  if (!Number.isFinite(time)) return <small>Retry scheduled</small>;
  const seconds = Math.max(0, Math.ceil((time - now) / 1000));
  return <small>{seconds > 0 ? `Retry in ${seconds} seconds` : 'Retry is due and waiting to be scheduled'}</small>;
}

export default function CaseStatus({ item }) {
  return <div className="suite-case-state">
    <ExecutionBadge status={item.execution_status} />
    {item.execution_status === 'retry_wait' && <RetryTime at={item.retry_at} />}
    {(item.phase || item.stage) && <small>{phaseLabels[item.stage] || phaseLabels[item.phase] || item.stage || item.phase}</small>}
    {item.current_step != null && <small>Turn {item.current_step}{item.total_steps != null ? ` of ${item.total_steps}` : ''}</small>}
    {(item.error || item.result?.error) && <small className="suite-error-text">{errorText(item.error || item.result?.error)}</small>}
    {item.recovery_reason && <small>{item.recovery_reason}</small>}
  </div>;
}

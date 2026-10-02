import { Button, Tag } from 'antd';
import { CheckCircleOutlined, ExclamationCircleOutlined, FileSearchOutlined } from '@ant-design/icons';

export default function ReplayJudgeCard({ report, onInspect }) {
  const status = report?.status?.toLowerCase() || 'unknown';
  const passed = status === 'pass';
  const issues = report?.issues || [];
  const gaps = report?.evidence_gaps || [];
  const Icon = passed ? CheckCircleOutlined : ['issue', 'fail'].includes(status) ? ExclamationCircleOutlined : FileSearchOutlined;
  return <section className={`replay-judge-card ${passed ? 'is-pass' : 'is-issue'}`} aria-label="Judge result">
    <div className="replay-judge-heading"><Icon /><div><small>JUDGE RESULT</small><h3>{passed ? 'Passed' : status === 'issue' ? 'Issues found' : report?.status || 'Unknown verdict'}</h3></div>
      {report?.confidence && <Tag>{report.confidence} confidence</Tag>}</div>
    {report?.summary && <p>{report.summary}</p>}
    {issues.length > 0 && <ul>{issues.slice(0, 2).map((issue, i) => <li key={issue.issue_id || i}>{issue.message || issue.description || issue.code || JSON.stringify(issue)}</li>)}</ul>}
    <div className="replay-judge-footer"><span>{issues.length} {issues.length === 1 ? 'issue' : 'issues'} · {gaps.length} evidence gaps</span>
      <Button type="text" size="small" onClick={onInspect}>View full report ↗</Button></div>
  </section>;
}

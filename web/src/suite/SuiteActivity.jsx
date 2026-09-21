import { SyncOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { Button } from 'antd';
import { ExecutionBadge } from './CaseStatus.jsx';
import { suiteActivity } from './activityModel.js';

export default function SuiteActivity({ cases, jobs, onCaseSelect, onAgentSelect, disconnected }) {
  const { active, preparing } = suiteActivity(cases, jobs);
  if (!active.length && !preparing.length) return null;
  return <section className="suite-activity" aria-label="Current activity">
    <div className="suite-activity-heading"><SyncOutlined spin={!disconnected} /><strong>{disconnected ? 'Last known activity' : 'In progress'}</strong></div>
    {active.map(item => <div className="suite-activity-item" key={item.key}>
      <span className="suite-activity-name">{item.agent_id} <strong> / Case {item.case_index + 1}</strong></span>
      <ExecutionBadge status={item.execution_status} />
      <Button type="link" onClick={() => onCaseSelect(item)}>View Case <ArrowRightOutlined /></Button>
    </div>)}
    {preparing.map(job => <div className="suite-activity-item" key={job.agent_id}>
      <span className="suite-activity-name">{job.agent_id}</span>
      <span>{job.generation_status === 'running' ? 'Generating Cases — execution has not started' : 'Preparing Agent — waiting for Case status'}</span>
      <Button type="link" onClick={() => onAgentSelect(job.agent_id)}>View Agent <ArrowRightOutlined /></Button>
    </div>)}
  </section>;
}

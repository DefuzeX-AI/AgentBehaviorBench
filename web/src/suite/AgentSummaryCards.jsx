import { ArrowRightOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { Button, Progress, Tag, Typography } from 'antd';
import { isActive } from './model.js';
import { ExecutionBadge } from './CaseStatus.jsx';
import { agentSummaries, formatDuration } from './summaryModel.js';

const { Text, Title } = Typography;
const colors = ['#137a5d', '#c76722', '#3d70c9', '#7357a6', '#a24e65', '#46747a'];
const colorFor = value => colors[[...value].reduce((sum, char) => sum + char.charCodeAt(0), 0) % colors.length];

export default function AgentSummaryCards({ cases, jobs, onSelect }) {
  const agents = agentSummaries(cases, jobs);
  return <section className="agent-summary-section" aria-label="Agents in Suite">
    <div className="suite-section-label"><Text>AGENTS IN SUITE</Text><Tag>{agents.length} {agents.length === 1 ? 'Agent' : 'Agents'}</Tag></div>
    <div className="agent-summary-grid">{agents.map(agent => <article className={`agent-summary-card${agent.status === 'running' ? ' is-running' : ''}`} key={agent.agent_id}>
      <div className="agent-card-header"><span className="agent-avatar" style={{ background: colorFor(agent.agent_id) }}>{agent.agent_id.charAt(0).toUpperCase()}</span>
        <div className="agent-card-title"><Title level={3}>{agent.agent_id}</Title>{agent.status === 'running' ? <ExecutionBadge status="running" /> : <Text type="secondary">{agent.status || `${agent.judged} judged`}</Text>}</div>
        <Tag color={agent.pass_rate == null ? 'default' : agent.pass_rate === 100 ? 'success' : 'warning'}>{agent.pass_rate == null ? 'No verdicts' : `${agent.pass_rate}% pass`}</Tag></div>
      <div className="agent-card-activity">{cases.filter(item => item.agent_id === agent.agent_id && isActive(item.execution_status)).map(item => `Case ${item.case_index + 1}`).join(", ")}</div>
      <div className="agent-card-progress"><div><Text type="secondary">{agent.total} {agent.total === 1 ? 'Case' : 'Cases'}</Text><Text type="secondary">{agent.completed}/{agent.total} done</Text></div>
        <Progress percent={agent.completion_rate} showInfo={false} strokeColor="#2f8f68" trailColor="#e2e7e3" size="small" /></div>
      <div className="agent-card-footer"><Text type="secondary"><ClockCircleOutlined /> {formatDuration(agent.average_duration_ms)}</Text>
        <Button type="link" onClick={() => onSelect(agent.agent_id)}>View Agent <ArrowRightOutlined /></Button></div>
    </article>)}</div>
  </section>;
}

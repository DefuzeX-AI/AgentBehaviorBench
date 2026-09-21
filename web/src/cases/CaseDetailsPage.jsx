import { Alert, Breadcrumb, Button, Select, Skeleton, Space, Tabs, Tag, Typography } from 'antd';
import { useDispatch, useSelector } from 'react-redux';
import useLiveJson from '../useLiveJson.js';
import { actions } from '../suite/store.js';
import { currentAttempt, errorText, executionStatus, reportOf } from '../suite/model.js';
import { ExecutionBadge, JudgeBadge } from '../suite/CaseStatus.jsx';
import { RetryButton } from '../suite/SuiteControls.jsx';
import CaseOverview from './CaseOverview.jsx';
import CaseConversation from './CaseConversation.jsx';
import CaseToolsFiles from './CaseToolsFiles.jsx';
import CaseJudge from './CaseJudge.jsx';
import CaseTrace from './CaseTrace.jsx';
import CaseRawJson from './CaseRawJson.jsx';
import './cases.css';

const { Text, Title } = Typography;

export default function CaseDetailsPage({ item, revision, onBack }) {
  const dispatch = useDispatch();
  const selectedId = useSelector(state => state.suite.selectedAttempts[item.key]);
  const detailTab = useSelector(state => state.suite.detailTab);
  const attempt = selectedId ? item.attempts.find(value => value.attempt_id === selectedId) : currentAttempt(item);
  const artifact = attempt?.artifact_run_id;
  const evaluation = useLiveJson(artifact ? `/api/observe/runs/${artifact}/evaluation` : null, revision);
  const rejected = attempt?.host_accepted === false || attempt?.host_acceptance === false || attempt?.host_acceptance === 'rejected';
  const report = evaluation.data?.judge || reportOf(attempt) || reportOf(item);
  const artifactLoading = Boolean(artifact && !evaluation.data && !evaluation.error);
  const loading = <Skeleton active paragraph={{ rows: 6 }} />;
  const tabs = [
    { key: 'overview', label: 'Overview', children: <CaseOverview item={item} attempt={attempt} data={evaluation.data} error={evaluation.error} /> },
    { key: 'conversation', label: 'Conversation', children: artifactLoading ? loading : <CaseConversation inputs={evaluation.data?.inputs} /> },
    { key: 'tools', label: 'Tools & Files', children: artifact ? <CaseToolsFiles run={artifact} revision={revision} inputs={evaluation.data?.inputs} /> : null },
    { key: 'judge', label: 'Judge', children: artifactLoading && !report ? loading : <CaseJudge report={report} item={attempt || item} /> },
    { key: 'trace', label: 'Trace', children: artifact ? <CaseTrace run={artifact} revision={revision} /> : null },
    { key: 'json', label: 'Raw JSON', children: artifactLoading ? loading : <CaseRawJson data={evaluation.data || attempt || item} /> },
  ];

  return <section className="case-details" aria-label={`${item.agent_id} Case ${item.case_index + 1}`}>
    <Breadcrumb items={[{ title: <Button type="link" className="case-back" onClick={onBack}>Suite overview</Button> }, { title: item.agent_id }, { title: `Case ${item.case_index + 1}` }]} />
    <div className="case-header"><div><Text className="case-eyebrow">{item.agent_id}</Text><Title level={1}>Case {item.case_index + 1}</Title>
      <Text copyable type="secondary">{item.case_id || 'Case ID pending'}</Text></div>
      <Space wrap><ExecutionBadge status={attempt ? executionStatus(attempt) : item.execution_status} /><JudgeBadge status={attempt?.judge_status || report?.status || item.judge_status} />{rejected && <Tag color="error">Host rejected</Tag>}<RetryButton item={item} /></Space></div>

    <div className="case-attempt-bar"><label><Text type="secondary">Execution attempt</Text><Select value={attempt?.attempt_id || ''} disabled={!item.attempts.length} onChange={value => dispatch(actions.attemptSelected({ key: item.key, attempt_id: value }))}
      options={item.attempts.map(value => ({ value: value.attempt_id, label: `Attempt ${value.attempt_number}${value.attempt_id === item.active_attempt_id ? ' (current)' : ''}` }))} placeholder="Execution has not started" /></label>
      {artifact && <Text type="secondary">Artifact run <Text copyable code>{artifact}</Text></Text>}</div>

    {attempt?.error && <Alert type="error" showIcon message="This attempt failed" description={errorText(attempt.error)} />}
    {!artifact && <Alert type="info" showIcon message="Execution artifacts are not available yet" description={attempt ? 'This attempt has no viewable artifact directory. Saved Suite state remains available below.' : 'Case execution has not started.'} />}

    <Tabs className="case-tabs" activeKey={detailTab} onChange={value => dispatch(actions.detailTabChanged(value))}
      items={tabs.map(tab => ({ ...tab, disabled: ['conversation', 'tools', 'trace'].includes(tab.key) && !artifact }))} />
  </section>;
}

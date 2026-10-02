import { Alert, Button, Space, Typography } from 'antd';
import { useDispatch, useSelector } from 'react-redux';
import { commandBlocksNew, controlCapability, resendSuiteCommand, sendSuiteCommand } from './commands.js';

export default function ReuseCaseControl({ item }) {
  const dispatch = useDispatch();
  const snapshot = useSelector(state => state.suite.snapshot);
  const active = useSelector(state => state.suite.command);
  const capability = controlCapability(snapshot, window.location.origin);
  if (!capability) return null;
  const matches = command => command?.action === 'reuse' && command.agent_id === item.agent_id
    && command.case_index === item.case_index;
  const saved = (snapshot.commands || []).findLast(matches);
  const command = matches(active) ? active : saved;
  const busy = commandBlocksNew('reuse', active) || commandBlocksNew('reuse', saved);
  return <Space orientation="vertical" style={{ width: '100%', marginBottom: 16 }}>
    <Space wrap>
      <Button disabled={!item.prepared_case?.artifact_path || busy}
        loading={Boolean(command && busy && command.status !== 'uncertain')}
        onClick={() => dispatch(sendSuiteCommand('reuse', item))}>Rerun this Case</Button>
      <Typography.Text type="secondary">Run Agent and Judge again. Join a compatible active reuse Suite, or start a new one.</Typography.Text>
    </Space>
    {command && <Alert showIcon type={command.status === 'rejected' ? 'error' : 'info'}
      message={`Case rerun: ${command.status}`} description={<Space orientation="vertical">
        {command.error && <span>{command.error}</span>}
        {command.status === 'uncertain' && <Button onClick={() => dispatch(resendSuiteCommand())}>Check request again</Button>}
        {command.result_url && <Typography.Link href={command.result_url}>Open reuse Suite</Typography.Link>}
        {command.result_path && <Typography.Text copyable code>{command.result_path}</Typography.Text>}
      </Space>} />}
  </Space>;
}

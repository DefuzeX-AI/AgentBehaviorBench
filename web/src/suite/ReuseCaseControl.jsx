import { Alert, Button, Space, Tooltip, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
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
  return <Space orientation="vertical" className="case-reuse-controls">
    <Space wrap>
      <Tooltip title="Run Agent and Judge again using this saved Case. Reuses a compatible active Suite when available.">
      <Button icon={<ReloadOutlined />} disabled={!item.prepared_case?.artifact_path || busy}
        loading={Boolean(command && busy && command.status !== 'uncertain')}
        onClick={() => dispatch(sendSuiteCommand('reuse', item))}>Rerun this Case</Button></Tooltip>
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

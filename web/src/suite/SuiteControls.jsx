import { useDispatch, useSelector } from 'react-redux';
import { Alert, Button, Space } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { commandInFlight, controlCapability, resendSuiteCommand, sendSuiteCommand } from './commands.js';

export function RetryButton({ item }) {
  const dispatch = useDispatch();
  const { snapshot, command, error } = useSelector(state => state.suite);
  const capability = controlCapability(snapshot, window.location.origin);
  if (!capability || !item.can_retry) return null;
  return <Button size="small" disabled={Boolean(error) || commandInFlight(command)} title={item.recovery_reason || undefined}
    onClick={event => { event.stopPropagation(); dispatch(sendSuiteCommand('retry', item)); }}>{item.recovery_action === 'resume_request' ? 'Resume request' : ['generate', 'generate_case'].includes(item.recovery_action) ? 'Generate missing Case' : 'Retry Case'}</Button>;
}

export function ExportReportButton() {
  const snapshot = useSelector(state => state.suite.snapshot);
  function download() {
    // Export only the result snapshot, never the session control credential.
    const { capabilities, ...report } = snapshot;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `${snapshot.suite_id || 'suite'}-report.json`; anchor.click();
    URL.revokeObjectURL(url);
  }
  return <Button icon={<DownloadOutlined />} disabled={!snapshot} onClick={download}>Export report</Button>;
}

export default function SuiteControls({ cases }) {
  const dispatch = useDispatch();
  const { snapshot, command, error } = useSelector(state => state.suite);
  const capability = controlCapability(snapshot, window.location.origin);
  const canResume = capability && snapshot.can_resume !== false && cases.some(item => !['completed', 'succeeded'].includes(item.execution_status));
  return <>
    {(canResume || !capability) && <Space className="suite-actions" wrap>
      {canResume && <Button type="primary" disabled={Boolean(error) || commandInFlight(command)}
        onClick={() => dispatch(sendSuiteCommand('resume'))}>Resume unfinished work</Button>}
      {!capability && <span className="suite-muted">Read-only view</span>}
    </Space>}
    {command && <Alert className="suite-command-alert" type={command.status === 'rejected' ? 'error' : command.status === 'uncertain' ? 'warning' : 'info'} showIcon message={
      command.status === 'sending' ? 'Sending recovery command…' : command.status === 'uncertain' ? 'Connection interrupted; command receipt is unconfirmed.' :
        command.status === 'rejected' ? 'Recovery command was not executed.' : ['completed', 'succeeded', 'finished'].includes(command.status) ? 'Recovery command processed; results continue to sync.' : 'Recovery command received and waiting for the scheduler.'}
      description={command.error && (typeof command.error === 'string' ? command.error : command.error.message)}
      action={command.status === 'uncertain' && capability ? <Button size="small" onClick={() => dispatch(resendSuiteCommand())}>Reconcile and resend</Button> : null} />}
  </>;
}

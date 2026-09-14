import { useDispatch, useSelector } from 'react-redux';
import { commandInFlight, controlCapability, resendSuiteCommand, sendSuiteCommand } from './commands.js';

export function RetryButton({ item }) {
  const dispatch = useDispatch();
  const { snapshot, command, error } = useSelector(state => state.suite);
  const capability = controlCapability(snapshot, window.location.origin);
  if (!capability || !item.can_retry) return null;
  return <button disabled={Boolean(error) || commandInFlight(command)} title={item.recovery_reason || undefined}
    onClick={() => dispatch(sendSuiteCommand('retry', item))}>{item.recovery_action === 'resume_request' ? '恢复请求' : ['generate', 'generate_case'].includes(item.recovery_action) ? '补生成' : '从头重试此 Case'}</button>;
}

export default function SuiteControls({ cases }) {
  const dispatch = useDispatch();
  const { snapshot, command, error } = useSelector(state => state.suite);
  const capability = controlCapability(snapshot, window.location.origin);
  function download() {
    // Export only the result snapshot, never the session control credential.
    const { capabilities, ...report } = snapshot;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = `${snapshot.suite_id || 'suite'}-report.json`; anchor.click();
    URL.revokeObjectURL(url);
  }
  return <>
    <div className="suite-actions">
      {capability && <button className="primary" disabled={Boolean(error) || commandInFlight(command) || snapshot.can_resume === false || !cases.some(item => !['completed', 'succeeded'].includes(item.execution_status))}
        onClick={() => dispatch(sendSuiteCommand('resume'))}>继续未完成</button>}
      <button disabled={!snapshot} onClick={download}>导出当前报告</button>
      {!capability && <span className="suite-muted">只读查看</span>}
    </div>
    {command && <div className={`suite-notice ${command.status === 'rejected' ? 'suite-command-error' : ''}`} role="status">
      {command.status === 'sending' ? '正在发送恢复命令…' : command.status === 'uncertain' ? '连接中断，尚未确认命令是否接收。' :
        command.status === 'rejected' ? '恢复命令未执行。' : ['completed', 'succeeded', 'finished'].includes(command.status) ? '恢复命令已处理，结果持续同步。' : '恢复命令已接收，等待调度器处理。'}
      {command.error && <span> {typeof command.error === 'string' ? command.error : command.error.message}</span>}
      {command.status === 'uncertain' && capability && <button onClick={() => dispatch(resendSuiteCommand())}>核对并重发原命令</button>}
    </div>}
  </>;
}

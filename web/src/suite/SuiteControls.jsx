import { useSelector } from 'react-redux';
import { Button } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';

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

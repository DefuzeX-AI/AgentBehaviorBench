import { useMemo, useState } from 'react';
import { Alert, Button, Modal, Segmented, Space, Tag, Typography } from 'antd';
import { ExpandOutlined } from '@ant-design/icons';
import { inspectFileDiff } from './fileDiffModel.js';
import FileContentPreview from './FileContentPreview.jsx';
import FileDiffView from './FileDiffView.jsx';
import './fileDiff.css';

export default function FileDiffViewer({ record, path }) {
  const model = useMemo(() => inspectFileDiff(record), [record]);
  const [mode, setMode] = useState(() => model.preview ? 'preview' : model.file ? 'diff' : 'raw');
  const [expanded, setExpanded] = useState(false), [layout, setLayout] = useState('unified');
  // Live evidence can change while this drawer remains open.
  const activeMode = mode === 'preview' && !model.preview ? (model.file ? 'diff' : 'raw') : mode === 'diff' && !model.file ? 'raw' : mode;
  const options = [...(model.preview ? [{ label: model.preview.side === 'before' ? 'Deleted content' : 'Preview', value: 'preview' }] : []),
    ...(model.file ? [{ label: 'Diff', value: 'diff' }] : []), { label: 'Raw patch', value: 'raw' }];
  const panel = <section className="file-diff-viewer">
    <div className="file-diff-heading"><strong>{path.replaceAll('\\', '/').split('/').at(-1)}</strong>
      <Space size={4}>{model.file && <><Tag color="green">+{model.additions}</Tag><Tag color="red">−{model.deletions}</Tag></>}</Space>
    </div>
    <div className="file-diff-toolbar">
      <Segmented aria-label="File display" value={activeMode} options={options} onChange={setMode} />
      <Space wrap>
        {expanded && activeMode === 'diff' && <Segmented aria-label="Diff layout" value={layout} onChange={setLayout}
          options={[{ label: 'Unified', value: 'unified' }, { label: 'Side by side', value: 'split' }]} />}
        <Typography.Text copyable={{ text: activeMode === 'preview' ? model.preview.content : model.patch }}>{activeMode === 'preview' ? 'Copy content' : 'Copy patch'}</Typography.Text>
        {!expanded && <Button icon={<ExpandOutlined />} onClick={() => setExpanded(true)}>Expand</Button>}
      </Space>
    </div>
    {model.error && <Alert type="info" showIcon message={model.error} />}
    {model.file && !model.preview && <p className="file-diff-note">Recorded changes only; a complete file preview is not available from this evidence.</p>}
    {activeMode === 'preview' && <p className="file-diff-note">{model.preview.side === 'before' ? 'Deleted file · content before deletion.' : 'New file · content after creation.'}</p>}
    <div className="file-diff-scroll">
      {activeMode === 'preview' ? <FileContentPreview path={path} content={model.preview.content} />
        : activeMode === 'diff' ? <FileDiffView file={model.file} layout={expanded ? layout : 'unified'} />
          : <pre className="file-raw-patch">{model.patch}</pre>}
    </div>
  </section>;
  return <>{expanded ? <Button icon={<ExpandOutlined />} onClick={() => setExpanded(false)}>Return to file details</Button> : panel}
    <Modal title="File changes" open={expanded} onCancel={() => setExpanded(false)} footer={null} width="95vw" destroyOnHidden>{expanded && panel}</Modal>
  </>;
}

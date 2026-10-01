import { FileOutlined, FolderOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';
import FileChangeTooltip from './FileChangeTooltip.jsx';
import { changeStyle } from './fileChangesModel.js';

export default function FileChangeCard({ change, snapshot, animate, onSelect }) {
  const style = changeStyle(change.type);
  const Icon = change.fileType === 'directory' ? FolderOutlined : FileOutlined;
  const basename = change.path.replaceAll('\\', '/').split('/').filter(Boolean).at(-1) || change.path;
  return <Tooltip title={<FileChangeTooltip change={change} snapshot={snapshot} />} trigger={['hover', 'focus']}>
    <button type="button" className={`file-change-card file-change-${style.tone}${animate ? ' file-change-arrived' : ''}`}
      aria-label={`${style.label} ${change.fileType || 'path'}: ${change.path}`} onClick={() => onSelect({ change, snapshot })}>
      <span className="file-change-icon" aria-hidden="true"><Icon /><b>{style.mark}</b></span>
      <span className="file-change-caption"><strong>{basename}</strong><small>{style.label} · {change.fileType || 'Unknown type'}</small></span>
    </button>
  </Tooltip>;
}

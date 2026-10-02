import { useEffect, useMemo, useRef, useState } from 'react';
import { Checkbox, Tree } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';
import { parentDirectories, replayFiles } from './replayFiles.js';

const changeNames = { A: 'Added', M: 'Modified', D: 'Deleted' };

export default function ReplayFiles({ entries, changes, latestEvent, workspace, selected, onSelect }) {
  const [changedOnly, setChangedOnly] = useState(false);
  const [expanded, setExpanded] = useState([]);
  const [height, setHeight] = useState(360);
  const list = useRef(null);
  const { tree, changedCount } = useMemo(() => replayFiles(entries, changes, changedOnly), [entries, changes, changedOnly]);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setHeight(Math.max(80, entry.contentRect.height)));
    if (list.current) observer.observe(list.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (latestEvent) setExpanded(keys => [...new Set([...keys, ...parentDirectories(latestEvent.changes.map(change => change.path))])]);
  }, [latestEvent]);
  return <aside className="replay-files" aria-label="Workspace files">
    <div className="replay-files-heading"><FolderOpenOutlined /><strong>Files</strong><span>{changedCount ? `${changedCount} changed` : `${entries.length} paths`}</span></div>
    <div className="replay-workspace" title={workspace}>{workspace || 'Workspace'}</div>
    <Checkbox checked={changedOnly} onChange={e => {
      setChangedOnly(e.target.checked);
      if (e.target.checked) setExpanded(parentDirectories(changes.map(change => change.path)));
    }}>Changes only</Checkbox>
    <div className="replay-tree-container" ref={list}>
      {tree.length ? <Tree.DirectoryTree height={height} blockNode showIcon treeData={tree} expandedKeys={expanded}
        selectedKeys={selected ? [selected] : []} onExpand={setExpanded}
        onSelect={(keys, { node }) => { if (node.isLeaf) onSelect(node.key); }}
        titleRender={node => <span className={`replay-tree-label ${node.change === 'D' ? 'is-deleted' : ''}`} title={node.key}>
          <span>{node.title}</span>{node.change ? <b className={`file-status-${node.change}`} aria-label={changeNames[node.change]}>{node.change}</b>
            : node.changedCount > 0 && <b className="file-change-count" aria-label={`${node.changedCount} changes inside`}>{node.changedCount}</b>}
        </span>} /> : <p className="replay-muted">{changedOnly ? 'No changes at this point.' : 'No recorded files.'}</p>}
    </div>
    <div className="replay-file-legend"><span className="file-status-A">A Added</span><span className="file-status-M">M Modified</span><span className="file-status-D">D Deleted</span></div>
  </aside>;
}

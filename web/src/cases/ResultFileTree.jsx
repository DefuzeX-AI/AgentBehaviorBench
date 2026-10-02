import { useState } from 'react';
import { Alert, Button, Spin } from 'antd';
import { CaretDownOutlined, CaretRightOutlined, FileOutlined, FolderOpenOutlined, FolderOutlined } from '@ant-design/icons';
import useLiveJson from '../useLiveJson.js';

function Directory({ run, path = '', name, revision, selected, onSelect, root = false }) {
  const [open, setOpen] = useState(root || Boolean(path && selected?.startsWith(`${path}/`)));
  const [offset, setOffset] = useState(0);
  const { data, error } = useLiveJson(open ? `/api/observe/runs/${run}/files?path=${encodeURIComponent(path)}&offset=${offset}` : null, revision, false);
  return <li className="result-directory">
    <button className="result-tree-row" aria-expanded={open} onClick={() => setOpen(value => !value)} title={path || run}>
      {open ? <CaretDownOutlined /> : <CaretRightOutlined />}{open ? <FolderOpenOutlined /> : <FolderOutlined />}<span>{name}</span>
    </button>
    {open && <ul>
      {error && <li><Alert type="warning" title="Directory unavailable" description={error} /></li>}
      {!data && !error && <li className="result-tree-loading"><Spin size="small" /></li>}
      {data?.entries.map(entry => entry.type === 'directory'
        ? <Directory key={entry.path} run={run} path={entry.path} name={entry.name} revision={revision} selected={selected} onSelect={onSelect} />
        : <li key={entry.path}><button className={`result-tree-row result-tree-file${entry.path === selected ? ' selected' : ''}`}
          aria-current={entry.path === selected ? 'true' : undefined} title={entry.path} onClick={() => onSelect(entry.path)}>
          <FileOutlined /><span>{entry.name}</span></button></li>)}
      {data && !data.total && <li className="result-tree-empty">Empty directory</li>}
      {(offset > 0 || data?.next != null) && <li className="result-tree-pages"><Button size="small" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 200))}>Previous</Button>
        <Button size="small" disabled={data?.next == null} onClick={() => setOffset(data.next)}>Next</Button></li>}
    </ul>}
  </li>;
}

export default function ResultFileTree(props) {
  return <nav className="result-file-tree" aria-label="Saved result file directory"><ul><Directory {...props} root name={`${props.run}/`} /></ul></nav>;
}

import { useState } from 'react';
import { Input, Segmented, Tree, Typography } from 'antd';
import { parseJson } from './protocols.js';

function branches(value, path = '$') {
  const object = value !== null && typeof value === 'object';
  return { key: path, title: <span><b>{path === '$' ? '$' : path.split('/').at(-1)}</b>{' : '}
    {object ? <span className="json-type">{Array.isArray(value) ? `Array(${value.length})` : `Object(${Object.keys(value).length})`}</span>
      : <span className={`json-${typeof value}`}>{typeof value === 'string' ? JSON.stringify(value) : String(value)}</span>}</span>,
    children: object ? Object.entries(value).map(([key, v]) => branches(v, `${path}/${key.replaceAll('~', '~0').replaceAll('/', '~1')}`)) : undefined };
}

export default function JsonValue({ value, label = 'JSON' }) {
  const [mode, setMode] = useState('Structure'), [search, setSearch] = useState('');
  const parsed = parseJson(value);
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  if (value == null) return <div className="missing-value">{label}: content not recorded</div>;
  // Avoid constructing a huge tree until the user asks for it; text remains complete.
  const large = (text?.length || 0) > 200000;
  const structured = typeof parsed === 'object' && parsed !== null;
  return <div className="json-viewer">
    <div className="json-tools"><span>{label}</span><Segmented size="small" value={mode} onChange={setMode} options={['Structure', 'Raw']} />
      <Typography.Text copyable={{ text: text || '' }}>Copy</Typography.Text></div>
    {mode === 'Structure' && structured ? large ? <><p>This content is large, so the complete text is shown by default.</p><pre>{JSON.stringify(parsed, null, 2)}</pre></> : <>
      <Input size="small" allowClear placeholder="Find a JSON field or value" value={search} onChange={e => setSearch(e.target.value)} />
      <Tree className="json-tree" treeData={[branches(parsed)]} defaultExpandedKeys={['$']} selectable={false}
        filterTreeNode={node => Boolean(search && JSON.stringify(node.key).toLowerCase().includes(search.toLowerCase()))} />
      {search && <pre className="json-search-results">{JSON.stringify(parsed, null, 2).split('\n').filter(line => line.toLowerCase().includes(search.toLowerCase())).join('\n') || 'No matching fields or values'}</pre>}
    </> : <pre>{structured && mode === 'Structure' ? JSON.stringify(parsed, null, 2) : text}</pre>}
  </div>;
}

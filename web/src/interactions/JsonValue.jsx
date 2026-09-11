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
  const [mode, setMode] = useState('结构'), [search, setSearch] = useState('');
  const parsed = parseJson(value);
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  if (value == null) return <div className="missing-value">{label}：未记录此内容</div>;
  // Avoid constructing a huge tree until the user asks for it; text remains complete.
  const large = (text?.length || 0) > 200000;
  const structured = typeof parsed === 'object' && parsed !== null;
  return <div className="json-viewer">
    <div className="json-tools"><span>{label}</span><Segmented size="small" value={mode} onChange={setMode} options={['结构', '原文']} />
      <Typography.Text copyable={{ text: text || '' }}>复制</Typography.Text></div>
    {mode === '结构' && structured ? large ? <><p>内容较大，默认使用完整文本显示。</p><pre>{JSON.stringify(parsed, null, 2)}</pre></> : <>
      <Input size="small" allowClear placeholder="定位 JSON 字段或值" value={search} onChange={e => setSearch(e.target.value)} />
      <Tree className="json-tree" treeData={[branches(parsed)]} defaultExpandedKeys={['$']} selectable={false}
        filterTreeNode={node => Boolean(search && JSON.stringify(node.key).toLowerCase().includes(search.toLowerCase()))} />
      {search && <pre className="json-search-results">{JSON.stringify(parsed, null, 2).split('\n').filter(line => line.toLowerCase().includes(search.toLowerCase())).join('\n') || '没有匹配的字段或值'}</pre>}
    </> : <pre>{structured && mode === '结构' ? JSON.stringify(parsed, null, 2) : text}</pre>}
  </div>;
}

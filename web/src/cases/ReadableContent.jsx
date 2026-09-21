import { useState } from 'react';
import { Button, Segmented, Space, Tag, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { inspectContent } from './contentFormat.js';

function Markdown({ children }) {
  return <div className="content-markdown"><ReactMarkdown skipHtml remarkPlugins={[remarkGfm]} components={{ img: () => null }}>{children}</ReactMarkdown></div>;
}

function JsonNode({ name, value, root = false }) {
  const [open, setOpen] = useState(root);
  const [limit, setLimit] = useState(50);
  const container = value !== null && typeof value === 'object';
  if (!container) return <div className="json-leaf"><strong>{name}: </strong><span className={`json-value json-${value === null ? 'null' : typeof value}`}>{JSON.stringify(value)}</span></div>;
  const keys = Object.keys(value);
  return <details className="json-branch" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary><strong>{name}</strong> <span>{Array.isArray(value) ? `Array [${keys.length}]` : `Object {${keys.length}}`}</span></summary>
    {open && <div className="json-children">{keys.slice(0, limit).map(key => <JsonNode key={key} name={key} value={value[key]} />)}
      {keys.length > limit && <Button size="small" onClick={() => setLimit(limit + 50)}>Show next {Math.min(50, keys.length - limit)} fields</Button>}
    </div>}
  </details>;
}

export default function ReadableContent({ value }) {
  const { raw, json, parsed, responseKey } = inspectContent(value);
  const [mode, setMode] = useState('readable');
  const options = [{ label: 'Readable', value: 'readable' }, ...(json ? [{ label: 'JSON', value: 'json' }] : []), { label: 'Raw', value: 'raw' }];
  return <div className="readable-content">
    <Space className="content-toolbar" wrap><Tag>{json ? 'JSON' : 'Text / Markdown'}</Tag><Segmented size="small" options={options} value={mode} onChange={setMode} /><Typography.Text copyable={{ text: raw }}>Copy original</Typography.Text></Space>
    {mode === 'raw' ? <pre className="content-raw">{raw}</pre>
      : mode === 'json' ? <pre className="content-raw">{JSON.stringify(parsed, null, 2)}</pre>
      : json ? <>
        {responseKey && <section className="content-response"><Typography.Text type="secondary">{responseKey}</Typography.Text><Markdown>{parsed[responseKey]}</Markdown></section>}
        <div className="content-tree" aria-label="Complete JSON structure"><JsonNode name="root" value={parsed} root={!responseKey} /></div>
      </> : <Markdown>{raw}</Markdown>}
  </div>;
}

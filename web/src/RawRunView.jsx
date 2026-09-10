import { useState, useEffect } from 'react';
import useLiveJson from './useLiveJson.js';

export default function RawRunView({ run, revision }) {
  const [cursor, setCursor] = useState(0);
  const { data, error } = useLiveJson(`/api/observe/runs/${run}/events?offset=${cursor}`, revision);
  useEffect(() => { setCursor(0); }, [run, revision]);
  return <section><h2>原始事件／网络</h2><p>每页最多 100 条，单条内容完整保留。按文件记录顺序分页。</p>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>读取中…</p>}
    {data?.warnings.map((w, i) => <p key={i}>{w}</p>)}
    {data?.events.map((e, i) => <details key={`${cursor}:${i}`}><summary>{cursor + i + 1} · {e.raw.source} · {e.raw.event} · {e.raw.timestamp}</summary><p>{e.file}</p><pre>{JSON.stringify(e.raw, null, 2)}</pre></details>)}
    <button disabled={!cursor} onClick={() => setCursor(0)}>回到第一页</button>
    <button disabled={data?.next == null} onClick={() => setCursor(data.next)}>下一页</button>
  </section>;
}

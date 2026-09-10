import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Modal } from 'antd';
import useLiveJson from '../useLiveJson.js';
import './evaluation.css';

const textValue = value => typeof value === 'string' ? value : null;

function JsonButton({ label, value, onOpen }) {
  return <button className="json-button" disabled={value == null} onClick={() => onOpen(label, value)}>查看 JSON</button>;
}

function MarkdownContent({ value, empty = '尚未产生内容。' }) {
  const text = textValue(value);
  if (text == null) return <p className="content-empty">{empty}</p>;
  return <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>;
}

function Status({ value }) {
  const tone = /succeed|complete|pass/i.test(String(value)) ? 'success' : /fail|error|issue/i.test(String(value)) ? 'issue' : 'neutral';
  return <span className={`status status-${tone}`}>{value || '未开始'}</span>;
}

function JudgeSummary({ report, onOpen }) {
  if (!report) return <section className="judge-summary"><h3>Judge 判决</h3><p className="content-empty">尚未产生 Judge 报告。</p></section>;
  const issues = Array.isArray(report.issues) ? report.issues : [];
  return <section className="judge-summary">
    <div className="section-heading"><div><p className="eyebrow">Judge</p><h3>判决结果 <Status value={report.status} /></h3></div><JsonButton label="Judge 报告" value={report} onOpen={onOpen} /></div>
    {report.stop_reason && <p className="judge-meta">结束原因：<code>{report.stop_reason}</code>{report.confidence && <> · 置信度：<code>{report.confidence}</code></>}</p>}
    {issues.length > 0 ? <ol className="judge-issues">{issues.map((issue, index) => <li key={issue.issue_id || index}><span className={`severity severity-${issue.severity || 'unknown'}`}>{issue.severity || '未知'}</span><span>{issue.message || '未提供说明'}</span></li>)}</ol> : <p className="judge-ok">Judge 没有报告问题。</p>}
  </section>;
}

export default function EvaluationView({ run, revision }) {
  const { data, error } = useLiveJson(run ? `/api/observe/runs/${run}/evaluation` : null, revision);
  const [json, setJson] = useState(null);
  if (!run) return <p>请先选择运行。</p>;
  if (error) return <p>{error}</p>;
  if (!data) return <p>正在读取评测产物…</p>;

  const openJson = (title, value) => setJson({ title, value });
  const manifest = data.manifest || {};
  return <section className="evaluation-view">
    <div className="evaluation-header">
      <div><p className="eyebrow">Case / SDK / Judge</p><h2>SDK 评测</h2><p>优先显示可读内容。需要排查字段或完整上下文时，再打开原始 JSON。</p></div>
      <div className="header-actions"><JsonButton label="当前阶段 / 错误" value={data.error || data.manifest} onOpen={openJson} /><JsonButton label="同容器进程与 SDK 版本" value={data.process} onOpen={openJson} /><JsonButton label="Case 原始记录" value={data.case} onOpen={openJson} /></div>
    </div>
    <div className="execution-status" aria-label="执行阶段">
      <div><span>执行</span><Status value={manifest.execution} /></div><div><span>OTel</span><Status value={manifest.otel} /></div><div><span>提交</span><Status value={manifest.submission} /></div><div><span>Judge</span><Status value={manifest.judge} /></div>
    </div>
    {data.inputs.map(step => <section className="input-step" key={step.step}>
      <div className="input-step-title"><p className="eyebrow">Input {step.step}</p><div className="step-identifiers"><code>{step.input?.input_id || '未关联 Input'}</code>{step.result?.status && <Status value={step.result.status} />}</div></div>
      <div className="content-panel input-panel"><div className="section-heading"><div><h3>输入</h3><p>SDK Input 的 <code>payload</code></p></div><JsonButton label={`Input ${step.step}`} value={step.input} onOpen={openJson} /></div><MarkdownContent value={step.input?.payload} empty="尚未产生 SDK Input。" /></div>
      <div className="content-panel output-panel"><div className="section-heading"><div><h3>Agent 结果</h3><p>Agent Result 的 <code>output</code></p></div><JsonButton label={`Agent 结果 ${step.step}`} value={step.result} onOpen={openJson} /></div><MarkdownContent value={step.result?.output} empty="尚未产生 Agent 输出。" /></div>
      <div className="supporting-json"><JsonButton label={`SDK Submission ${step.step}`} value={step.submission} onOpen={openJson} /><JsonButton label={`KUMA Evidence ${step.step}`} value={step.evidence} onOpen={openJson} /></div>
    </section>)}
    <JudgeSummary report={data.judge} onOpen={openJson} />
    <p className="evaluation-footnote">调用树请切换至 OTel。Judge 判决与执行状态会分别记录。</p>
    <Modal title={json?.title} open={Boolean(json)} onCancel={() => setJson(null)} footer={null} width={880} destroyOnHidden><pre className="json-modal-content">{json && JSON.stringify(json.value, null, 2)}</pre></Modal>
  </section>;
}

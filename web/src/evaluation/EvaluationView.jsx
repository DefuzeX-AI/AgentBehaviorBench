import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Modal } from 'antd';
import useLiveJson from '../useLiveJson.js';
import './evaluation.css';

const textValue = value => typeof value === 'string' ? value : null;

function JsonButton({ label, value, onOpen }) {
  return <button className="json-button" disabled={value == null} onClick={() => onOpen(label, value)}>View JSON</button>;
}

function MarkdownContent({ value, empty = 'No content has been produced yet.', collapse = false }) {
  const text = textValue(value);
  if (text == null) return <p className="content-empty">{value == null ? empty : 'This content is structured data. View the JSON for details.'}</p>;
  return <CollapsibleMarkdown text={text} collapse={collapse} />;
}

function CollapsibleMarkdown({ text, collapse }) {
  const [expanded, setExpanded] = useState(false);
  const canCollapse = collapse && (text.length > 360 || text.split('\n').length > 5);
  return <>
    <div className={`markdown-content ${canCollapse && !expanded ? 'is-collapsed' : ''}`}><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>
    {canCollapse && <button className="content-toggle" onClick={() => setExpanded(value => !value)} aria-expanded={expanded}>{expanded ? 'Collapse prompt' : 'Show full prompt'}</button>}
  </>;
}

function Status({ value }) {
  const tone = /succeed|complete|pass/i.test(String(value)) ? 'success' : /fail|error|issue/i.test(String(value)) ? 'issue' : 'neutral';
  return <span className={`status status-${tone}`}>{value || 'Not provided'}</span>;
}

function SdkIdentity({ process }) {
  const sdk = process?.sdk || process?.sdk_name || process?.evaluator || (process?.mode === 'official' ? 'kuma' : 'Not recorded');
  const version = process?.sdk_version ? `v${process.sdk_version}` : 'Version not recorded';
  const mode = process?.mode === 'official' ? 'Official run' : process?.mode || 'Run mode not recorded';
  return <span className="sdk-identity"><strong>{sdk} SDK</strong><span>{version}</span><span>{mode}</span></span>;
}

function JudgeSummary({ report, onOpen }) {
  if (!report) return <section className="judge-summary"><h3>Judge verdict</h3><p className="content-empty">No Judge report has been produced yet.</p></section>;
  const issues = Array.isArray(report.issues) ? report.issues : [];
  return <section className="judge-summary">
    <div className="section-heading"><div><p className="eyebrow">Judge</p><h3>Verdict <Status value={report.status} /></h3></div><JsonButton label="Judge report" value={report} onOpen={onOpen} /></div>
    {report.stop_reason && <p className="judge-meta">Stop reason: <code>{report.stop_reason}</code>{report.confidence && <> · Confidence: <code>{report.confidence}</code></>}</p>}
    {issues.length > 0 ? <ol className="judge-issues">{issues.map((issue, index) => <li key={issue.issue_id || index}><span className={`severity severity-${issue.severity || 'unknown'}`}>{issue.severity || 'Unknown'}</span><span>{issue.message || 'No description provided'}</span></li>)}</ol> : <p className="judge-ok">The Judge reported no issues.</p>}
  </section>;
}

export default function EvaluationView({ run, revision }) {
  const { data, error } = useLiveJson(run ? `/api/observe/runs/${run}/evaluation` : null, revision);
  const [json, setJson] = useState(null);
  if (!run) return <p>Select a run first.</p>;
  if (error && !data) return <p role="alert">{error} (retrying automatically)</p>;
  if (!data) return <p>Loading evaluation artifacts…</p>;

  const openJson = (title, value) => setJson({ title, value });
  const manifest = data.manifest || {};
  const publicReport = data.public_result?.report;
  return <section className="evaluation-view">
    {error && <p role="alert">{error}; showing the last data and resuming sync when the connection recovers.</p>}
    <div className="evaluation-header">
      <div><p className="eyebrow">Case / SDK / Judge</p><h2>SDK evaluation</h2><p>Readable content is shown first. Open the raw JSON when you need complete fields or context.</p></div>
      <div className="header-actions"><JsonButton label="Current phase / error" value={data.error || data.manifest} onOpen={openJson} /><JsonButton label="Container process and SDK version" value={data.process} onOpen={openJson} /><JsonButton label="Raw Case record" value={data.case} onOpen={openJson} /></div>
    </div>
    <div className="execution-status" aria-label="Execution phases">
      <div><span>Execution</span><Status value={manifest.execution || data.execution_status} /></div><div><span>OTel</span><Status value={manifest.otel} /></div><div><span>Submission</span><Status value={manifest.submission} /></div><div><span>Judge</span><Status value={manifest.judge || publicReport?.status} /></div>
    </div>
    {data.inputs.map(step => <section className="input-step" key={step.step}>
      <div className="input-step-title"><div><p className="eyebrow">Input {step.step}</p><SdkIdentity process={data.process} /></div><div className="step-identifiers"><code>{step.input?.input_id || 'Unlinked Input'}</code>{step.result?.status && <Status value={step.result.status} />}</div></div>
      <div className="content-panel input-panel"><div className="section-heading"><div><h3>Input</h3><p>The SDK Input <code>payload</code>; only the first five lines are shown by default</p></div><JsonButton label={`Input ${step.step}`} value={step.input} onOpen={openJson} /></div><MarkdownContent value={step.input?.payload} empty="No SDK Input has been produced yet." collapse /></div>
      <div className="content-panel output-panel"><div className="section-heading"><div><h3>Agent result</h3><p>The Agent Result <code>output</code></p></div><JsonButton label={`Agent result ${step.step}`} value={step.result} onOpen={openJson} /></div><MarkdownContent value={step.result?.output} empty="No Agent output has been produced yet." /></div>
      <div className="supporting-json"><JsonButton label={`SDK Submission ${step.step}`} value={step.submission} onOpen={openJson} /><JsonButton label={`KUMA Evidence ${step.step}`} value={step.evidence} onOpen={openJson} /></div>
    </section>)}
    <JudgeSummary report={data.judge || data.public_result?.report} onOpen={openJson} />
    <p className="evaluation-footnote">Switch to OTel for the call tree. Judge verdicts and execution status are recorded separately.</p>
    <Modal title={json?.title} open={Boolean(json)} onCancel={() => setJson(null)} footer={null} width={880} destroyOnHidden><pre className="json-modal-content">{json && JSON.stringify(json.value, null, 2)}</pre></Modal>
  </section>;
}

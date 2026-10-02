import { Alert, Typography } from 'antd';
import { CheckCircleOutlined, ExclamationCircleOutlined, FileSearchOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import JudgeProgress from './JudgeProgress.jsx';
import ReadableContent from './ReadableContent.jsx';
import { judgeProgress } from './judgeProgress.js';
import { judgeLabel, judgeReportModel, judgeReportUnavailable, judgeTone } from './judgeReportModel.js';
import './judge.css';

function Status({ value }) {
  return value == null ? null : <span className={`judge-status is-${judgeTone(value)}`}>{judgeLabel(value)}</span>;
}

function Evidence({ references }) {
  if (!references.length) return null;
  return <details className="judge-evidence"><summary>{references.length} evidence {references.length === 1 ? 'reference' : 'references'}</summary>
    <ul>{references.map((reference, index) => <li key={index}>
      {reference && typeof reference === 'object' && !Array.isArray(reference)
        && (reference.evidence_index != null || reference.pointer) ? <>
          {reference.evidence_index != null && <strong>Evidence {String(reference.evidence_index)}</strong>}
          {reference.pointer && <code>{String(reference.pointer)}</code>}
          {reference.evidence_sha256 && <Typography.Text copyable code>{String(reference.evidence_sha256)}</Typography.Text>}
        </> : <ReadableContent value={reference} />}
    </li>)}</ul>
  </details>;
}

function Findings({ title, findings, kind }) {
  if (!findings.length) return null;
  return <section className="judge-section" aria-label={title}><h3>{title} <span>{findings.length}</span></h3>
    <div className="judge-findings-list">{findings.map((finding, index) => <article className={`judge-finding is-${kind}`} key={`${finding.id}-${index}`}>
      <div className="judge-finding-heading"><strong>{finding.title || `${kind === 'issue' ? 'Issue' : 'Gap'} ${index + 1}`}</strong><Status value={finding.severity} /></div>
      {finding.message ? <p>{finding.message}</p> : <ReadableContent value={finding.raw} />}
      <Evidence references={finding.evidence} />
    </article>)}</div>
  </section>;
}

function Assessment({ model }) {
  if (!model.dimensions.length && !model.attributions.length) return null;
  return <section className="judge-section" aria-label="Judge assessment"><h3>Assessment</h3>
    {model.dimensions.length > 0 && <div className="judge-dimensions">{model.dimensions.map(dimension => <article className="judge-dimension" key={dimension.key}>
      <h4>{dimension.title}</h4><Status value={dimension.status} />
      {(dimension.severity != null || dimension.confidence != null) && <div className="judge-dimension-meta">
        {dimension.severity != null && <span>{judgeLabel(dimension.severity)} severity</span>}
        {dimension.confidence != null && <span>Confidence: {dimension.confidence}</span>}
      </div>}
      {dimension.reason && <p>{dimension.reason}</p>}
      {dimension.reasonCodes.length > 0 && <div className="judge-reasons">{dimension.reasonCodes.map((reason, index) => <span key={index}>{judgeLabel(reason)}</span>)}</div>}
      <Evidence references={dimension.evidence} />
    </article>)}</div>}
    {model.attributions.length > 0 && <details className="judge-disclosure"><summary>Reported causes <span>{model.attributions.length}</span></summary>
      <div className="judge-causes">{model.attributions.map(cause => <article key={cause.key}>
        <strong>{cause.title}</strong>{cause.confidence != null && <span>Confidence: {cause.confidence}</span>}
        {cause.reason && <p>{cause.reason}</p>}<Evidence references={cause.evidence} />
      </article>)}</div>
    </details>}
  </section>;
}

function Steps({ steps }) {
  if (!steps.length) return null;
  return <section className="judge-section" aria-label="Reported steps"><h3>Steps <span>{steps.length}</span></h3>
    <ol className="judge-steps">{steps.map((step, index) => <li key={`${step.id}-${index}`}>
      <div className="judge-step-heading"><strong>{step.id}</strong>{step.status && <span className="judge-step-state"><small>{step.statusLabel}</small><Status value={step.status} /></span>}</div>
      {step.reason && <p>{step.reason}</p>}
      {step.issues.length > 0 && <ul className="judge-step-issues">{step.issues.map((issue, number) => <li key={number}>
        {issue.id && <code>{issue.id}</code>}{issue.message || (!issue.id && <ReadableContent value={issue.raw} />)}
      </li>)}</ul>}
      {(step.traceStatus != null || step.traceSpans != null) && <div className="judge-dimension-meta">
        {step.traceStatus != null && <span>Trace: {judgeLabel(step.traceStatus)}</span>}
        {step.traceSpans != null && <span>{step.traceSpans} spans</span>}
      </div>}
      <Evidence references={step.evidence} />
    </li>)}</ol>
  </section>;
}

export default function CaseJudge({ report, item = {} }) {
  if (!report) {
    if (judgeProgress(item)) return <JudgeProgress item={item} />;
    const missing = judgeReportUnavailable(item);
    return <Alert type={missing.type} showIcon title={missing.title} description={missing.description} />;
  }
  const model = judgeReportModel(report);
  const rejected = item.host_accepted === false || item.host_acceptance === false || item.host_acceptance === 'rejected';
  const Icon = model.tone === 'pass' ? CheckCircleOutlined : model.tone === 'issue' ? ExclamationCircleOutlined
    : model.status === 'insufficient_evidence' ? FileSearchOutlined : QuestionCircleOutlined;
  return <div className="judge-report">
    {rejected && <Alert type="warning" showIcon title="Host rejected this execution" description="This retained report is not an accepted benchmark result." />}
    <section className={`judge-result is-${model.tone}`} aria-label="Judge verdict">
      <div className="judge-result-heading"><div className="judge-result-title"><Icon aria-hidden="true" /><div><span className="case-eyebrow">JUDGE RESULT</span><h2>{model.verdict}</h2></div></div>
        {model.confidence != null && <div className="judge-confidence"><span>Confidence</span><strong>{judgeLabel(model.confidence)}</strong></div>}
      </div>
      {model.summary && <p className="judge-summary">{model.summary}</p>}
    </section>
    <Findings title="Issues" findings={model.issues} kind="issue" />
    <Findings title="Evidence gaps" findings={model.gaps} kind="gap" />
    <Assessment model={model} />
    <Steps steps={model.steps} />
    {model.metadata.length > 0 && <details className="judge-disclosure"><summary>Report details</summary><dl className="judge-metadata">
      {model.metadata.map(field => <div key={field.label}><dt>{field.label}</dt><dd><Typography.Text copyable>{field.value}</Typography.Text></dd></div>)}
    </dl></details>}
    <details className="judge-disclosure judge-raw"><summary>Full report · JSON</summary><ReadableContent value={model.raw} /></details>
  </div>;
}

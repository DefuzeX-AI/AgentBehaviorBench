import { useEffect, useState } from 'react';
import { Spin } from 'antd';
import useLiveJson from '../useLiveJson.js';
import ReadableContent from '../cases/ReadableContent.jsx';
import { coverageNotes, inputSections, provenanceNote, shouldPoll, stepTitle, stepTone } from './trajectoryModel.js';
import './trajectory.css';

function ToolLog({ log }) {
  return <details className="trajectory-tool">
    <summary><code>{log.tool_name}</code> <span className={`status status-${log.execution_status === 'succeeded' ? 'success' : log.execution_status === 'error' ? 'issue' : 'neutral'}`}>{log.execution_status}</span>
      {log.exit_status && <span className="trajectory-exit">exit {log.exit_status.exitCode ?? '?'}{log.exit_status.signal ? ` · ${log.exit_status.signal}` : ''}</span>}
      {log.link !== 'exact' && <em>link {log.link}</em>}</summary>
    <h5>Arguments</h5><ReadableContent value={log.input_arguments} />
    <h5>Outputs</h5>{log.outputs == null ? <p className="content-empty">No output was observed.</p> : <ReadableContent value={log.outputs} />}
  </details>;
}

function Step({ step }) {
  const [section, setSection] = useState('output');
  const sections = step.kind === 'model' ? ['input', 'output'] : [];
  return <details className={`trajectory-step tone-${stepTone(step)}`}>
    <summary><span className="trajectory-step-id">Step {step.step_id}</span><strong>{step.agent_name}</strong>
      <span className="trajectory-kind">{step.kind}{step.model ? ` · ${step.model}` : ''}</span><span className="trajectory-title">{stepTitle(step)}</span></summary>
    <div className="trajectory-step-body">
      <p className="trajectory-meta">{step.started_at || 'no timestamp'}{step.ended_at ? ` → ${step.ended_at}` : ''} · source {step.source}{step.output_source === 'framework' ? ' (output from framework span)' : ''}{step.purpose && step.purpose !== 'unknown' ? ` · purpose ${step.purpose}` : ''}</p>
      {step.output?.wire_error && <p role="alert">Interceptor recorded a transport failure: {step.output.wire_error.error_code || 'unknown'}{step.output.wire_error.error ? ` – ${step.output.wire_error.error}` : ''}</p>}
      {sections.length > 0 && <div className="payload-buttons">{sections.map(key => <button key={key} aria-pressed={section === key} onClick={() => setSection(key)}>{key === 'input' ? 'Model input (complete)' : 'Model output'}</button>)}</div>}
      {step.kind === 'model' && section === 'input' && <ReadableContent key={`${step.step_id}:input`} value={step.input} />}
      {step.kind === 'model' && section === 'output' && <>
        {step.output?.reasoning && <details><summary>Reasoning</summary><ReadableContent value={step.output.reasoning} /></details>}
        {typeof step.output?.text === 'string' && step.output.text ? <ReadableContent value={step.output.text} /> : <p className="content-empty">No answer text; see tool calls below.</p>}
        {step.output?.tool_calls?.length > 0 && <details><summary>{step.output.tool_calls.length} tool calls emitted{step.output.tool_calls_source ? ` (${step.output.tool_calls_source})` : ''}</summary><ReadableContent value={step.output.tool_calls} /></details>}
        {step.output?.usage && <p className="trajectory-meta">usage {JSON.stringify(step.output.usage)}</p>}
      </>}
      {step.tool_logs?.length > 0 && <div className="trajectory-tools"><h4>Tool executions</h4>{step.tool_logs.map((log, i) => <ToolLog key={log.tool_call_id || i} log={log} />)}</div>}
      <details><summary>Evidence identifiers</summary><pre>{JSON.stringify(step.evidence, null, 2)}</pre></details>
    </div>
  </details>;
}

// `live` is true while the attempt is still executing: the saved trajectory.json does not exist yet,
// so the view polls until the route stops answering `pending` and then shows the file once.
export default function TrajectoryView({ run, revision, live = false }) {
  const [latest, setLatest] = useState(null);
  const { data, error, updated } = useLiveJson(run ? `/api/observe/runs/${run}/trajectory` : null, revision, shouldPoll(latest, live));
  useEffect(() => { setLatest(data); }, [data]);
  if (!run) return <section className="empty">Select a run on the left to inspect its trajectory.</section>;
  if (error && !data) return <p role="alert">{error}</p>;
  if (!data) return <p>Loading the trajectory…</p>;
  if (data.status === 'pending') return <section className="empty trajectory-pending" role="status" aria-live="polite">
    <h2><Spin size="small" /> Execution in progress</h2>
    <p>{data.reason || 'trajectory.json is written once the attempt finishes.'} This tab checks every second and shows the trajectory as soon as it is saved{updated ? ` (last check ${updated})` : ''}.</p>
  </section>;
  if (data.status === 'failed') return <section className="empty"><h2>Trajectory unavailable</h2><p>{data.error_type}: {data.error}</p></section>;
  const metadata = data.metadata || {};
  const configuration = metadata.agent_configuration || {};
  const tools = (configuration.tools || []).map(t => t?.name || t?.function?.name).filter(Boolean);
  const provenance = provenanceNote(data);
  return <section aria-label="Trajectory" className="trajectory">
    <div className="trace-tabs"><small>{data.schema} · status {data.status} · {data.steps.length} steps · synced {updated || 'waiting'}</small>
      <span className={`trajectory-provenance tone-${provenance.tone}`}>{provenance.text}</span></div>
    <p className="trajectory-meta">{coverageNotes(data).join(' · ')}</p>
    {data.warnings?.length > 0 && <details className="warnings"><summary>{data.warnings.length} builder warnings</summary><ul>{data.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>}
    <details className="trajectory-metadata"><summary>Run metadata: {data.agent_id} ({data.framework}){tools.length ? ` · ${tools.length} tools` : ''}</summary>
      <h4>Task instruction</h4><ReadableContent value={metadata.task_instruction} />
      <h4>Agents</h4><p>{(configuration.agents || []).map(a => a.agent_name).join(', ') || data.agent_id}</p>
      {configuration.system_prompt != null && <details><summary>System prompt</summary><ReadableContent value={configuration.system_prompt} /></details>}
      {tools.length > 0 && <details><summary>Tool definitions ({tools.join(', ')})</summary><ReadableContent value={configuration.tools} /></details>}
      <details><summary>Architecture and runtime</summary><pre>{JSON.stringify({ system_architecture: metadata.system_architecture, runtime: configuration.runtime, notes: metadata.notes }, null, 2)}</pre></details>
    </details>
    {inputSections(data).map(section => <section key={section.ordinal ?? 'unassigned'} className="trajectory-input">
      <h3>{section.ordinal ? `Input ${section.ordinal}${section.inputId ? ` (${section.inputId})` : ''}` : 'Steps not assigned to an input'}{section.steps.length ? ` · steps ${section.steps[0].step_id}–${section.steps[section.steps.length - 1].step_id}` : ' · no steps'}</h3>
      {section.prompt != null && <details><summary>Prompt</summary><ReadableContent value={section.prompt} /></details>}
      {section.steps.map(step => <Step key={step.step_id} step={step} />)}
      {section.result && <details className="trajectory-result"><summary>Result: <span className={`status status-${section.result.status === 'succeeded' ? 'success' : 'issue'}`}>{section.result.status || 'unknown'}</span></summary>
        {section.result.error && <p role="alert">{section.result.error_type}: {section.result.error}</p>}
        <ReadableContent value={section.result.output} /></details>}
      {section.fileChanges.length > 0 && <details><summary>{section.fileChanges.length} file changes</summary>{section.fileChanges.map((change, i) => <details key={i}><summary>{change.change_type} {change.path} <small>({change.source})</small></summary>{change.diff ? <pre>{change.diff}</pre> : <p className="content-empty">No diff captured; blobs {change.before_sha256?.slice(0, 12) || '–'} → {change.after_sha256?.slice(0, 12) || '–'}.</p>}</details>)}</details>}
    </section>)}
    <details><summary>Derived from {data.sources?.length || 0} source files</summary><pre>{JSON.stringify(data.sources, null, 2)}</pre></details>
  </section>;
}

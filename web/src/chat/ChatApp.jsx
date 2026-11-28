import { App as AntApp, Button, Checkbox, Dropdown, Empty, Input, Modal, Popconfirm, Spin, Tag, Tooltip, Typography } from 'antd';
import {
  ArrowsAltOutlined, CodeOutlined, CopyOutlined, DeleteOutlined, DownloadOutlined, DownOutlined, FlagFilled,
  FolderOutlined, InfoCircleOutlined, MessageOutlined, PoweroffOutlined, QuestionCircleOutlined, RightOutlined,
  RobotOutlined, SendOutlined, SettingOutlined, UserOutlined,
} from '@ant-design/icons';
import { useEffect, useMemo, useRef, useState } from 'react';
import ReplayMessage from '../cases/ReplayMessage.jsx';
import useLiveJson from '../useLiveJson.js';
import {
  clarificationChoices, delegatedReplies, flattenTrajectory, formatDateTime, formatTime, ownerUnknown, parseComposer, PHASE_LABELS, recordSources, SOURCE_TITLES,
  STEP_TITLES, stepKind, stepMarks, stepSummary, trajectoryStats,
} from './chatModel.js';
import './chat.css';

function useCommand(api, token) {
  return async (path, body) => {
    const response = await fetch(`${api}${path}`, {
      method: 'POST', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-ABB-Control-Token': token },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  };
}

function RawData({ load, dark }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(null);
  const [error, setError] = useState('');
  const toggle = async () => {
    setOpen(!open);
    if (!open && value === null) {
      try { setValue(await load()); } catch (e) { setError(e.message); }
    }
  };
  return <div className={`chat-raw ${dark ? 'dark' : ''}`}>
    <button type="button" className="chat-raw-toggle" onClick={toggle}>{open ? <DownOutlined /> : <RightOutlined />}<span>{'{ }'}</span> Raw data</button>
    {open && (error ? <div className="chat-raw-error">{error}</div>
      : value === null ? <Spin size="small" /> : <pre>{JSON.stringify(value, null, 2)}</pre>)}
  </div>;
}

function AgentReply({ output, request, delegated, awaitingChoice, disabled, onChoose }) {
  const hasText = output != null && (typeof output !== 'string' || !!output.trim());
  return <div className="chat-agent-body">
    {hasText && <ReplayMessage value={output} />}
    {request ? <div className="chat-choice" role="group" aria-label={request.question}>
      <p>{awaitingChoice ? 'Please choose an option.' : 'Options offered'}</p>
      {request.context && <p>{request.context}</p>}
      <strong>{request.question}</strong>
      <div className="chat-choice-options">{request.options.map(option =>
        <Button key={option} disabled={disabled} onClick={() => onChoose(option)}>{option}</Button>
      )}</div>
    </div> : !hasText && <p>{delegated ? 'Handed off to a subagent.' : 'No direct reply recorded.'}</p>}
  </div>;
}

function Conversation({ state, trajectory, api, onSend, sending }) {
  const [text, setText] = useState('');
  const [json, setJson] = useState(false);
  const [error, setError] = useState('');
  const [selectedTurn, setSelectedTurn] = useState(null);
  const choices = useMemo(() => clarificationChoices(trajectory?.document), [trajectory?.document]);
  const replies = useMemo(() => delegatedReplies(trajectory?.document), [trajectory?.document]);
  const bottom = useRef(null);
  const followReplies = useRef(true);
  const turns = state?.turns || [];
  const canSend = state?.phase === 'ready' && !sending;
  // Scroll only the message list; scrollIntoView would also move the page.
  useEffect(() => {
    const list = bottom.current?.parentElement;
    if (list && followReplies.current) list.scrollTop = list.scrollHeight;
  }, [turns.length, turns.at(-1)?.status, replies]);
  const loadRaw = turn => async () => {
    const response = await fetch(`${api}/turns/${turn}/raw`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Record unavailable (HTTP ${response.status})`);
    return response.json();
  };
  const send = async () => {
    const parsed = parseComposer(text, json);
    if (parsed.error) { setError(parsed.error); return; }
    setError('');
    if (await onSend(parsed.value)) { setText(''); followReplies.current = true; }
  };
  return <section className="chat-pane">
    <header className="chat-pane-header"><MessageOutlined /><strong>Conversation</strong>
      <span className="chat-agent-id">{state?.agent_id}</span>
      <Tag className={`chat-phase ${state?.phase}`}>{PHASE_LABELS[state?.phase] || 'Connecting'}</Tag></header>
    <div className="chat-messages" onScroll={({ currentTarget: list }) => {
      followReplies.current = list.scrollHeight - list.clientHeight - list.scrollTop < 40;
    }}>
      {!turns.length && <div className="chat-empty">The Agent is running. Send a message to start the conversation.</div>}
      {turns.map(turn => <div className="chat-turn" key={turn.turn}>
        <div className="chat-user">
          <div className="chat-bubble">
            <div className="chat-bubble-head"><UserOutlined /><strong>You</strong><time>{formatTime(turn.sent_at)}</time></div>
            <div className="chat-bubble-body">{typeof turn.input === 'string' ? turn.input : <pre>{JSON.stringify(turn.input, null, 2)}</pre>}</div>
            {turn.status !== 'pending' && <RawData dark load={async () => { const raw = await loadRaw(turn.turn)(); return { input: raw.input, request: raw.request }; }} />}
          </div>
        </div>
        <div className="chat-agent">
          <div className="chat-agent-head"><RobotOutlined /><strong>Agent</strong><time>{formatTime(turn.answered_at)}</time></div>
          {turn.status === 'pending' ? <div className="chat-thinking"><Spin size="small" /> Replying…</div>
            : turn.status === 'succeeded' ? <AgentReply output={turn.output} request={choices.get(turn.turn)} delegated={replies.has(turn.turn)}
                awaitingChoice={turn === turns.at(-1) && state.phase === 'ready' && selectedTurn !== turn.turn}
                disabled={!canSend || turn !== turns.at(-1) || selectedTurn === turn.turn}
                onChoose={async option => {
                  setSelectedTurn(turn.turn);
                  if (!await onSend(option)) setSelectedTurn(null);
                }} />
              : <div className="chat-agent-error">Reply failed ({turn.status}): {turn.error}</div>}
          {turn.status !== 'pending' && <RawData load={async () => (await loadRaw(turn.turn)()).result ?? {}} />}
        </div>
        {Array.from(replies.get(turn.turn)?.values() || [], reply =>
          <div className="chat-agent chat-subagent" key={reply.id}>
            <div className="chat-agent-head"><RobotOutlined /><strong>{reply.name}</strong><time>{formatTime(reply.timestamp)}</time></div>
            <div className="chat-agent-body">{reply.message ? <ReplayMessage value={reply.message} />
              : <span className="chat-thinking">No subagent reply recorded{state.phase === 'ended' ? '.' : ' yet.'}</span>}</div>
          </div>)}
      </div>)}
      {state?.phase === 'stopped' && <div className="chat-agent-error">The chat stopped: {state.error}. End the chat to save its records.</div>}
      <div ref={bottom} />
    </div>
    <div className="chat-composer">
      <Input.TextArea value={text} onChange={event => setText(event.target.value)} autoSize={{ minRows: 3, maxRows: 10 }}
        variant="borderless" placeholder={json ? 'Enter one JSON value as the native Agent input' : 'Describe the task and include any context or file contents it needs'}
        onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (canSend) send(); } }} />
      {error && <div className="chat-composer-error">{error}</div>}
      <div className="chat-composer-bar">
        <Tooltip title="Enter sends, Shift+Enter adds a line. Each message is one turn in the same Agent session."><QuestionCircleOutlined /></Tooltip>
        <Checkbox checked={json} onChange={event => setJson(event.target.checked)}>JSON input</Checkbox>
        <Button className="chat-send" icon={<SendOutlined />} disabled={!canSend || !text.trim()} loading={sending} onClick={send}>Send</Button>
      </div>
    </div>
  </section>;
}

// The records that hold a step or a tool call's execution, one small label each.
function Sources({ item }) {
  const sources = recordSources(item);
  if (!sources.length) return null;
  return <span className="step-sources">{sources.map(source =>
    <Tooltip key={source} title={SOURCE_TITLES[source] || source}><span className={`step-source ${source}`}>{source}</span></Tooltip>)}</span>;
}

function StepCard({ row, canMark, onMark, onUnmark, onExpand }) {
  const { step } = row;
  const kind = stepKind(step);
  const [systemOpen, setSystemOpen] = useState(false);
  const Title = kind === 'system' ? 'button' : 'span';
  const marks = stepMarks(step);
  const unknown = ownerUnknown(step);
  // Marks are written into the saved trajectory, which exists once the chat has ended.
  const menu = { items: [{ key: 'mark', icon: <FlagFilled />, disabled: !canMark,
    label: canMark ? 'Mark this step…' : 'Mark this step (available after the chat ends)' },
  ...(canMark ? marks.map((mark, index) => ({ key: `unmark:${index}`, icon: <DeleteOutlined />, label: `Remove mark: ${mark.reason.slice(0, 24)}` })) : [])],
  onClick: ({ key }) => key === 'mark' ? onMark(row) : onUnmark(row, marks[Number(key.slice(7))]) };
  const icon = { user: <UserOutlined />, system: <SettingOutlined />, tool: <CodeOutlined />, assistant: <RobotOutlined /> }[kind];
  return <Dropdown menu={menu} trigger={['contextMenu']}>
    <article className={`step-card ${kind} ${marks.length ? 'marked' : ''} ${unknown ? 'owner-unknown' : ''}`} style={{ marginLeft: row.depth * 16 }}>
      <header>
        <Title className="step-title" {...(kind === 'system' && {
          type: 'button', 'aria-expanded': systemOpen, onClick: () => setSystemOpen(open => !open),
        })}>
          {kind === 'system' && <RightOutlined rotate={systemOpen ? 90 : 0} aria-hidden />}
          {icon}<strong>{STEP_TITLES[kind]}</strong><span className="step-id">#{step.step_id}</span>
          {row.depth > 0 && <Tag>{row.agent}</Tag>}
          {marks.length > 0 && <Tag color="orange" icon={<FlagFilled />}>Marked</Tag>}
          {unknown && <Tooltip title="No record shows which Agent made this step. It may belong to a subagent, not to the main Agent.">
            <Tag color="red" icon={<QuestionCircleOutlined />}>Owner unknown</Tag></Tooltip>}
          <time>{formatTime(step.timestamp)}</time><Sources item={step} /></Title>
        <Tooltip title="View full step"><button type="button" className="step-expand" onClick={() => onExpand(step)}><ArrowsAltOutlined /></button></Tooltip>
      </header>
      {(kind !== 'system' || systemOpen) && <>
      {step.model_name && <div className="step-model">{step.model_name}</div>}
      {step.reasoning_content && <details className="step-reasoning"><summary>Reasoning</summary><div>{step.reasoning_content}</div></details>}
      {typeof step.message === 'string' && step.message.trim() && <div className="step-message">{kind === 'user' || kind === 'system' ? step.message : <ReplayMessage value={step.message} />}</div>}
      {step.tool_calls?.map(call => <div className="step-tool" key={call.tool_call_id}>
        <div className="step-tool-name"><CodeOutlined /> <strong>{call.function_name}</strong><Sources item={call} /></div>
        <pre>{JSON.stringify(call.arguments, null, 2)}</pre>
      </div>)}
      {step.observation?.results?.map((result, index) => <details className="step-observation" key={index}>
        <summary>Result{result.source_call_id ? ` · ${result.source_call_id}` : ''}</summary>
        <pre>{typeof result.content === 'string' ? result.content : JSON.stringify(result.content, null, 2)}</pre>
      </details>)}
      {step.metrics && <div className="step-metrics">Input {step.metrics.prompt_tokens ?? '—'} · Output {step.metrics.completion_tokens ?? '—'}{step.metrics.cached_tokens ? ` · Cached ${step.metrics.cached_tokens}` : ''} tokens</div>}
      </>}
      {marks.map(mark => <div className="step-mark" key={mark.created_at}><FlagFilled /><span className="step-mark-reason">{mark.reason}</span>
        {canMark && <Tooltip title="Remove mark"><button type="button" className="step-unmark" onClick={() => onUnmark(row, mark)}><DeleteOutlined /></button></Tooltip>}</div>)}
    </article>
  </Dropdown>;
}

function PathRow({ label, path }) {
  const { message } = AntApp.useApp();
  return <div className="record-row">
    <span>{label}</span>
    <code>{path}</code>
    <Tooltip title="Copy path"><button type="button" className="record-copy" onClick={() => navigator.clipboard?.writeText(path).then(() => message.success('Copied'))}><CopyOutlined /></button></Tooltip>
  </div>;
}

// The end-of-chat dialog names only the trajectory and the run directory holding everything else.
function EndedPaths({ state }) {
  const result = state.result || {};
  return <div className="records">
    {result.error && <div className="chat-agent-error">{result.error}</div>}
    {state.trajectory_path ? <PathRow label="ATIF trajectory" path={state.trajectory_path} />
      : <div className="chat-agent-error">ATIF trajectory not saved ({result.atif?.status || 'unavailable'}){result.atif?.error ? `: ${result.atif.error}` : ''}</div>}
    <PathRow label="Run directory" path={state.directory} />
  </div>;
}

function Workbench({ state, trajectory, onEnd, onShowPaths, onMark, onUnmark }) {
  const [follow, setFollow] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const document = trajectory?.document;
  const rows = useMemo(() => flattenTrajectory(document), [document]);
  const stats = useMemo(() => trajectoryStats(document), [document]);
  // The panel scrolls on its own; while Follow is on, every refreshed preview keeps its end in view.
  const panel = useRef(null);
  useEffect(() => {
    if (follow && panel.current) panel.current.scrollTo({ top: panel.current.scrollHeight, behavior: 'smooth' });
  }, [document, follow]);
  const exportDocument = () => {
    const blob = new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' });
    const link = Object.assign(window.document.createElement('a'), { href: URL.createObjectURL(blob), download: 'trajectory.atif.json' });
    link.click();
    URL.revokeObjectURL(link.href);
  };
  const ending = state?.phase === 'ending';
  const ended = state?.phase === 'ended';
  const trajectoryBody = !document
    ? <div className="trajectory-empty">{trajectory?.status === 'pending' || !trajectory ? <Empty description="The trajectory appears after the first reply" />
      : <Typography.Text type="danger">Trajectory unavailable ({trajectory.status}): {trajectory.error}</Typography.Text>}</div>
    : <>
      <div className="trajectory-toolbar">
        <span>{stats.modelCalls} model {stats.modelCalls === 1 ? 'call' : 'calls'} · {stats.subagents} {stats.subagents === 1 ? 'subagent' : 'subagents'}</span>
        <span className="trajectory-tools">
          <Tag color={trajectory.saved ? 'green' : 'blue'}>{trajectory.saved ? 'Saved' : 'Live preview'}</Tag>
          <Tooltip title={stats.issues.length ? stats.issues.map(issue => `${issue.code}: ${issue.message}`).join('\n') : 'No recorded issues'}>
            <span className="trajectory-issues"><InfoCircleOutlined /> {stats.issues.length}</span></Tooltip>
          <Button size="small" type="text" icon={<DownloadOutlined />} onClick={exportDocument}>Export</Button>
          <Button size="small" type={follow ? 'default' : 'text'} icon={<DownOutlined />} onClick={() => setFollow(!follow)}>Follow</Button>
        </span>
      </div>
      {trajectory.warning && <div className="trajectory-warning">Preview not refreshed: {trajectory.warning}</div>}
      <div className="trajectory-hint">{trajectory.saved ? 'Right-click a step to mark it with a reason; the mark is written to trajectory.atif.json immediately.'
        : 'Live preview. Steps can be marked once the chat ends and trajectory.atif.json is saved.'}</div>
      <div className="trajectory-steps">
        {rows.map(row => <StepCard key={`${row.trajectoryId}:${row.step.step_id}`} row={row} canMark={!!trajectory.saved}
          onMark={onMark} onUnmark={onUnmark} onExpand={setExpanded} />)}
      </div>
    </>;
  return <section className="workbench">
    <header className="workbench-header"><strong>Workbench</strong>
      {ended ? <Button size="small" icon={<FolderOutlined />} onClick={onShowPaths}>Record paths</Button>
        : <Popconfirm title="End the chat?" description="The Agent container stops, then the trajectory and all records are saved." okText="End" cancelText="Cancel"
          onConfirm={onEnd} disabled={!state || state.phase === 'starting' || ending}>
          <Button danger size="small" icon={<PoweroffOutlined />} loading={ending}>End chat</Button></Popconfirm>}
    </header>
    <div className="workbench-meta">{formatDateTime(state?.turns?.[0]?.sent_at) || 'Waiting for the first turn'}{state?.run_id && <span> · {state.run_id}</span>}</div>
    <div className="workbench-section"><span><RightOutlined rotate={90} /> Trajectory</span></div>
    {/* Scrolling up by hand stops following, so the reader is not pulled back to the end. */}
    <div className="workbench-body" ref={panel} onWheel={event => { if (event.deltaY < 0 && follow) setFollow(false); }}>{trajectoryBody}</div>
    <Modal open={!!expanded} onCancel={() => setExpanded(null)} footer={null} width={760} title={expanded ? `Step #${expanded.step_id}` : ''}>
      <pre className="step-json">{expanded && JSON.stringify(expanded, null, 2)}</pre>
    </Modal>
  </section>;
}

function ChatPage({ api, token }) {
  const { message, modal } = AntApp.useApp();
  const command = useCommand(api, token);
  const [revision, setRevision] = useState(0);
  const state = useLiveJson(`${api}/state`, revision).data;
  const trajectory = useLiveJson(`${api}/trajectory`, revision).data;
  const [sending, setSending] = useState(false);
  const [marking, setMarking] = useState(null);
  const [reason, setReason] = useState('');
  const [width, setWidth] = useState(58);
  const shown = useRef(false);

  // The trajectory and the run directory holding every other record.
  const showPaths = () => modal.success({ title: 'Chat ended', width: 720, content: <EndedPaths state={state} />, okText: 'OK' });
  useEffect(() => {
    if (state?.phase === 'ended' && !shown.current) {
      shown.current = true;
      showPaths();
    }
  }, [state, modal]);

  const refresh = () => setRevision(value => value + 1);
  const send = async value => {
    setSending(true);
    try { await command('/turns', { input: value }); refresh(); return true; }
    catch (error) { message.error(error.message); return false; }
    finally { setSending(false); }
  };
  const end = async () => {
    try { await command('/end'); refresh(); } catch (error) { message.error(error.message); }
  };
  const saveMark = async () => {
    if (!reason.trim()) { message.warning('Enter a reason for the mark'); return; }
    try {
      await command('/marks', { trajectory_id: marking.trajectoryId, step_id: marking.step.step_id, reason });
      message.success('Mark written to trajectory.atif.json');
      setMarking(null); setReason(''); refresh();
    } catch (error) { message.error(error.message); }
  };
  const unmark = async (row, mark) => {
    try {
      await command('/marks/delete', { trajectory_id: row.trajectoryId, step_id: row.step.step_id, created_at: mark.created_at });
      message.success('Mark removed from trajectory.atif.json'); refresh();
    }
    catch (error) { message.error(error.message); }
  };
  const drag = event => {
    event.preventDefault();
    const move = moveEvent => setWidth(Math.min(75, Math.max(30, (moveEvent.clientX / window.innerWidth) * 100)));
    const stop = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', stop); };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', stop);
  };

  return <div className="chat-layout" style={{ gridTemplateColumns: `${width}% 8px minmax(0, 1fr)` }}>
    <Conversation state={state} trajectory={trajectory} api={api} onSend={send} sending={sending} />
    <div className="chat-divider" onMouseDown={drag} role="separator" aria-orientation="vertical" />
    <Workbench state={state} trajectory={trajectory} onEnd={end} onShowPaths={showPaths} onUnmark={unmark}
      onMark={row => { setMarking(row); setReason(''); }} />
    <Modal open={!!marking} title={marking ? `Mark step #${marking.step.step_id} (${STEP_TITLES[stepKind(marking.step)]})` : ''}
      okText="Save mark" cancelText="Cancel" onOk={saveMark} onCancel={() => setMarking(null)} destroyOnHidden>
      {marking && <div className="mark-preview">{stepSummary(marking.step).summary || '(no text)'}</div>}
      <Input.TextArea autoFocus value={reason} onChange={event => setReason(event.target.value)} autoSize={{ minRows: 4, maxRows: 10 }}
        maxLength={4000} showCount placeholder="Why this step is marked, e.g. it called an unnecessary tool, or the reply contradicts the facts" />
    </Modal>
  </div>;
}

export default function ChatApp({ api, token }) {
  return <AntApp><ChatPage api={api} token={token} /></AntApp>;
}

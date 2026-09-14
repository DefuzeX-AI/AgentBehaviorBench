import { actions } from './store.js';

export const commandInFlight = command => ['sending', 'accepted', 'queued', 'running', 'uncertain'].includes(command?.status);

export function controlCapability(snapshot, origin) {
  const capability = snapshot?.capabilities || {};
  if (!capability.can_control || !capability.control_url || !capability.control_token) return null;
  let url;
  try { url = new URL(capability.control_url, origin); } catch { return null; }
  if (url.origin !== origin) return null;
  return { ...capability, control_url: `${url.pathname}${url.search}` };
}

// An uncertain HTTP outcome must resend the same command identity, never a new job.
export function sendSuiteCommand(action, item, dependencies = {}) {
  return async (dispatch, getState) => {
    const state = getState().suite;
    const origin = dependencies.origin || window.location.origin;
    const capability = controlCapability(state.snapshot, origin);
    if (!capability || commandInFlight(state.command)) return;
    const command = {
      command_id: (dependencies.uuid || (() => crypto.randomUUID()))(), action,
      ...(item ? { agent_id: item.agent_id, case_index: item.case_index } : {}),
      ...(Number.isFinite(state.snapshot.revision) ? { expected_revision: state.snapshot.revision } : {}),
    };
    await deliver(command, capability, dispatch, dependencies.fetch || fetch);
  };
}

export function resendSuiteCommand(dependencies = {}) {
  return async (dispatch, getState) => {
    const state = getState().suite;
    if (state.command?.status !== 'uncertain') return;
    const capability = controlCapability(state.snapshot, dependencies.origin || window.location.origin);
    if (!capability) return;
    const { command_id, action, agent_id, case_index, expected_revision } = state.command;
    await deliver({ command_id, action, agent_id, case_index, expected_revision }, capability, dispatch, dependencies.fetch || fetch);
  };
}

async function deliver(command, capability, dispatch, request) {
  dispatch(actions.commandStarted(command));
  try {
    const response = await request(capability.control_url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-ABB-Control-Token': capability.control_token },
      body: JSON.stringify(command),
    });
    const body = await response.json();
    if (!response.ok) {
      dispatch(actions.commandFinished({ command_id: command.command_id,
        status: response.status >= 500 || response.status === 408 ? 'uncertain' : 'rejected',
        error: body.error?.message || body.error || `HTTP ${response.status}` }));
      return;
    }
    dispatch(actions.commandFinished({ ...body, command_id: command.command_id, status: body.status || 'accepted' }));
  } catch (error) {
    dispatch(actions.commandFinished({ command_id: command.command_id, status: 'uncertain', error: `未确认命令是否接收：${error.message}` }));
  }
}

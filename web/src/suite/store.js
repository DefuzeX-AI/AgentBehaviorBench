import { configureStore, createSlice } from '@reduxjs/toolkit';
import { normalizeCases, currentAttempt } from './model.js';

const initialState = {
  endpoint: null, snapshot: null, error: '', updated: null,
  selectedCaseKey: null, selectedAttempts: {}, detailTab: 'overview',
  filters: { query: '', agents: [], statuses: [], judges: [], attention: false, retried: false },
  table: { page: 1, pageSize: 10, field: 'case', order: 'ascend' }, command: null,
};

const suiteSlice = createSlice({
  name: 'suite', initialState,
  reducers: {
    endpointChanged(state, { payload }) {
      if (state.endpoint !== payload) return { ...initialState, endpoint: payload };
    },
    snapshotReceived(state, { payload: { snapshot, updated } }) {
      if (!snapshot || !Array.isArray(snapshot.jobs)) return;
      const old = state.snapshot;
      // A bound endpoint must never silently swap to a different Suite.
      if (old?.suite_id && old.suite_id !== snapshot.suite_id) {
        state.error = 'Returned Suite identity does not match this page; existing data was retained.';
        return;
      }
      if (Number.isFinite(old?.revision) && (!Number.isFinite(snapshot.revision) || snapshot.revision < old.revision)) return;
      state.error = '';
      state.updated = updated;
      if (!old || old.revision == null || snapshot.revision !== old.revision) state.snapshot = snapshot;
      else {
        // A viewer restart can change its capability token without a Case event.
        if (JSON.stringify(old.capabilities) !== JSON.stringify(snapshot.capabilities)) state.snapshot.capabilities = snapshot.capabilities;
        if (old.can_resume !== snapshot.can_resume) state.snapshot.can_resume = snapshot.can_resume;
        if (JSON.stringify(old.commands) !== JSON.stringify(snapshot.commands)) state.snapshot.commands = snapshot.commands;
      }
      // Keep an explicitly selected historical attempt across live updates.
      for (const item of normalizeCases(snapshot)) {
        if (state.selectedCaseKey === item.key && !state.selectedAttempts[item.key]) {
          state.selectedAttempts[item.key] = currentAttempt(item)?.attempt_id || null;
        }
      }
      if (state.selectedCaseKey && !normalizeCases(snapshot).some(item => item.key === state.selectedCaseKey)) {
        state.selectedCaseKey = null;
        state.detailTab = 'overview';
      }
      const commands = Array.isArray(snapshot.commands) ? snapshot.commands : Object.values(snapshot.commands || {});
      const received = commands.find(command => command.command_id === state.command?.command_id);
      if (received && state.command) state.command = { ...state.command, ...received };
    },
    connectionFailed(state, { payload }) { state.error = payload; },
    suiteSelected(state) { state.selectedCaseKey = null; state.detailTab = 'overview'; },
    caseSelected(state, { payload: item }) {
      state.selectedCaseKey = item.key;
      state.detailTab = 'overview';
      if (!state.selectedAttempts[item.key]) state.selectedAttempts[item.key] = currentAttempt(item)?.attempt_id || null;
    },
    detailTabChanged(state, { payload }) { state.detailTab = payload; },
    attemptSelected(state, { payload }) { state.selectedAttempts[payload.key] = payload.attempt_id; },
    filterChanged(state, { payload }) {
      state.filters = { ...state.filters, ...payload };
      state.table.page = 1;
    },
    filtersReset(state) {
      state.filters = initialState.filters;
      state.table.page = 1;
    },
    tableChanged(state, { payload }) { state.table = { ...state.table, ...payload }; },
    commandStarted(state, { payload }) { state.command = { ...payload, status: 'sending', error: '' }; },
    commandFinished(state, { payload }) {
      if (state.command?.command_id === payload.command_id) state.command = { ...state.command, ...payload };
    },
  },
});

export const actions = suiteSlice.actions;
export const suiteReducer = suiteSlice.reducer;
export const createSuiteStore = () => configureStore({ reducer: { suite: suiteReducer } });
export const suiteStore = createSuiteStore();

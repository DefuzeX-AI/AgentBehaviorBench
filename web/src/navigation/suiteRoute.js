export const DEFAULT_CASE_TAB = 'judge';
export const CASE_TABS = ['judge', 'overview', 'timing', 'replay', 'conversation', 'generation', 'tools', 'json'];

export function normalizeCaseTab(tab) {
  if (tab === 'trace') return 'timing';
  return CASE_TABS.includes(tab) ? tab : DEFAULT_CASE_TAB;
}

export function readSuiteRoute(cases, hash = window.location.hash, agentIds = cases.map(item => item.agent_id)) {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const caseValue = params.get('case');
  if (caseValue == null) return agentIds.includes(params.get('agent'))
    ? { item: null, agent: params.get('agent'), tab: 'overview' } : { item: null, tab: 'overview' };
  const caseIndex = Number(caseValue);
  const item = cases.find(candidate => candidate.agent_id === params.get('agent') && candidate.case_index === caseIndex) || null;
  if (!item) return { item: null, tab: 'overview' };
  const requestedTab = params.get('tab');
  const attempt = item.attempts?.find(a => a.attempt_id === params.get('attempt'));
  return { item, tab: normalizeCaseTab(requestedTab),
    ...(attempt ? { attemptId: attempt.attempt_id } : {}) };
}

export function suiteRouteHref(item, tab = DEFAULT_CASE_TAB, locationValue = window.location, attemptId = null) {
  const params = new URLSearchParams();
  if (item) {
    params.set('agent', item.agent_id);
    if (item.case_index != null) {
      params.set('case', String(item.case_index));
      params.set('tab', normalizeCaseTab(tab));
      if (attemptId) params.set('attempt', attemptId);
    }
  }
  return `${locationValue.pathname}${locationValue.search}${params.size ? `#${params}` : ''}`;
}

export function writeSuiteRoute(item, tab, mode = 'replace', attemptId = null) {
  const href = suiteRouteHref(item, tab, window.location, attemptId);
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (href === current) return;
  window.history[mode === 'push' ? 'pushState' : 'replaceState']({ abbView: item ? 'case' : 'suite' }, '', href);
}

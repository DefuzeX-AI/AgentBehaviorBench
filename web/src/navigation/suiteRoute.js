export const CASE_TABS = ['overview', 'conversation', 'tools', 'judge', 'trace', 'json'];

export function readSuiteRoute(cases, hash = window.location.hash) {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const caseValue = params.get('case');
  if (caseValue == null) return { item: null, tab: 'overview' };
  const caseIndex = Number(caseValue);
  const item = cases.find(candidate => candidate.agent_id === params.get('agent') && candidate.case_index === caseIndex) || null;
  if (!item) return { item: null, tab: 'overview' };
  const requestedTab = params.get('tab');
  return { item, tab: CASE_TABS.includes(requestedTab) ? requestedTab : 'overview' };
}

export function suiteRouteHref(item, tab = 'overview', locationValue = window.location) {
  const params = new URLSearchParams();
  if (item) {
    params.set('agent', item.agent_id);
    params.set('case', String(item.case_index));
    params.set('tab', CASE_TABS.includes(tab) ? tab : 'overview');
  }
  return `${locationValue.pathname}${locationValue.search}${params.size ? `#${params}` : ''}`;
}

export function writeSuiteRoute(item, tab, mode = 'replace') {
  const href = suiteRouteHref(item, tab);
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (href === current) return;
  window.history[mode === 'push' ? 'pushState' : 'replaceState']({ abbView: item ? 'case' : 'suite' }, '', href);
}

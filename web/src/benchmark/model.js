import { evaluatorName } from '../suite/evaluationSource.js';

export function evaluatorTabName(evaluator) {
  const reserved = { '@mixed': 'Mixed sources', '@not_recorded': 'Not recorded', '@partial': 'Partial records' };
  return reserved[evaluator.id] || evaluatorName(evaluator.id);
}

export function selectedEvaluator(evaluators, requested) {
  return evaluators.find(value => value.id === requested) || evaluators[0] || null;
}

export function evaluatorHref(id, locationValue) {
  const params = new URLSearchParams(locationValue.search);
  params.set('sdk', id);
  return `${locationValue.pathname}?${params}${locationValue.hash || ''}`;
}

export function caseVolume(agent) {
  const counts = agent.suites.map(suite => suite.case_count);
  if (!counts.length) return 'No Suites';
  if (counts.every(count => count === counts[0])) {
    return `${counts.length} ${counts.length === 1 ? 'Suite' : 'Suites'} × ${counts[0]} ${counts[0] === 1 ? 'Case' : 'Cases'}`;
  }
  return `${counts.length} Suites · ${Math.min(...counts)}–${Math.max(...counts)} Cases per Suite`;
}

export function caseProgress(total, completed) {
  const percent = total > 0 ? completed / total * 100 : null;
  const label = percent === null ? 'No Cases' : completed === total ? '100%'
    : completed === 0 ? '0%' : percent < 1 ? '<1%' : percent > 99 ? '>99%' : `${Math.round(percent)}%`;
  return { percent, label, incomplete: Math.max(0, total - completed) };
}

export function groundTruthProgress(value) {
  const metrics = value || {};
  const status = metrics.status || 'not_configured';
  const states = { not_configured: 'Not configured', empty: 'No known defects', invalid: 'Needs attention',
    not_assessed: 'Not assessed', partially_assessed: 'Partly assessed', assessed: 'Assessed' };
  const state = states[status] || 'Not assessed';
  const configured = !['not_configured', 'invalid'].includes(status);
  const count = metrics.defect_count || 0;
  const assessed = metrics.assessed_defect_count || 0;
  const hasResult = count > 0 && assessed > 0 && metrics.discovery_rate != null;
  const { percent, label } = hasResult ? caseProgress(count, metrics.discovered_defect_count || 0) : { percent: null, label: '—' };
  const detail = count > 0 ? `${assessed} of ${count} defects assessed` : state;
  const found = hasResult ? (metrics.discovered_defect_count || 0).toLocaleString() : '—';
  return { known: configured ? count.toLocaleString() : '—', found, percent, label, state, detail,
    description: hasResult ? `${metrics.discovered_defect_count || 0} discovered of ${count} known defects; ${detail}` : `${state}; discovery rate unavailable` };
}

import test from 'node:test';
import assert from 'node:assert/strict';
import { caseVolume, caseProgress, evaluatorHref, evaluatorTabName, groundTruthProgress, selectedEvaluator } from './model.js';

test('SDK tab selection keeps each SDK’s Case totals and discoveries independent', () => {
  const groups = [
    { id: 'kuma', totals: { case_count: 17 }, ground_truth: { discovered_defect_count: 1 } },
    { id: 'local', totals: { case_count: 1 }, ground_truth: { discovered_defect_count: 0 } },
  ];
  assert.equal(selectedEvaluator(groups, 'local').totals.case_count, 1);
  assert.equal(selectedEvaluator(groups, 'local').ground_truth.discovered_defect_count, 0);
  assert.equal(selectedEvaluator(groups, null).id, 'kuma');
  assert.equal(selectedEvaluator(groups, 'removed-sdk').id, 'kuma');
  assert.equal(selectedEvaluator([], 'kuma'), null);
});

test('SDK tab links preserve other URL state and encode custom SDK names', () => {
  const href = evaluatorHref('custom:sdk', { pathname: '/', search: '?sdk=local&view=saved', hash: '#section' });
  assert.equal(href, '/?sdk=custom%3Asdk&view=saved#section');
  assert.equal(new URL(href, 'http://localhost').searchParams.get('sdk'), 'custom:sdk');
});

test('unattributed SDK tabs stay explicit instead of claiming KUMA results', () => {
  assert.equal(evaluatorTabName({ id: 'kuma' }), 'KUMA');
  assert.equal(evaluatorTabName({ id: 'local' }), 'Local');
  assert.equal(evaluatorTabName({ id: 'my-sdk' }), 'my-sdk');
  assert.equal(evaluatorTabName({ id: '@mixed', evaluation_source: { sdks: ['kuma', 'local'] } }), 'Mixed sources');
  assert.equal(evaluatorTabName({ id: '@partial' }), 'Partial records');
  assert.equal(evaluatorTabName({ id: '@not_recorded' }), 'Not recorded');
});

test('equal Suite sizes show the multiplication behind the Case total', () => {
  assert.equal(caseVolume({ suites: [{ case_count: 10 }, { case_count: 10 }] }), '2 Suites × 10 Cases');
});

test('different Suite sizes report their range without inventing a uniform Case count', () => {
  assert.equal(caseVolume({ suites: [{ case_count: 10 }, { case_count: 3 }] }), '2 Suites · 3–10 Cases per Suite');
});

test('empty and single Suite volumes are explicit', () => {
  assert.equal(caseVolume({ suites: [] }), 'No Suites');
  assert.equal(caseVolume({ suites: [{ case_count: 0 }] }), '1 Suite × 0 Cases');
  assert.equal(caseVolume({ suites: [{ case_count: 1 }] }), '1 Suite × 1 Case');
});

test('completion visual distinguishes zero data from zero completed Cases', () => {
  assert.deepEqual(caseProgress(0, 0), { percent: null, label: 'No Cases', incomplete: 0 });
  assert.deepEqual(caseProgress(10, 0), { percent: 0, label: '0%', incomplete: 10 });
  assert.equal(caseProgress(18, 16).label, '89%');
});

test('small segments stay proportional and incomplete Cases never display 100%', () => {
  assert.deepEqual(caseProgress(200, 199), { percent: 99.5, label: '>99%', incomplete: 1 });
  assert.equal(caseProgress(300, 1).label, '<1%');
  assert.ok(caseProgress(300, 1).percent > 0);
  assert.deepEqual(caseProgress(200, 200), { percent: 100, label: '100%', incomplete: 0 });
});

test('missing ground truth and unassessed defects never display a zero discovery rate', () => {
  for (const status of ['not_configured', 'invalid', 'empty', 'not_assessed']) {
    const value = groundTruthProgress({ status, defect_count: status === 'not_assessed' ? 3 : 0, assessed_defect_count: 0, discovery_rate: null });
    assert.equal(value.percent, null);
    assert.equal(value.found, '—');
    assert.equal(value.label, '—');
  }
  assert.equal(groundTruthProgress().state, 'Not configured');
  assert.equal(groundTruthProgress({ status: 'not_assessed', defect_count: 3 }).known, '3');
});

test('explicit negative assessments can show zero while partial coverage keeps its denominator', () => {
  const negative = groundTruthProgress({ status: 'assessed', defect_count: 3, assessed_defect_count: 3, discovered_defect_count: 0, discovery_rate: 0 });
  assert.equal(negative.label, '0%');
  assert.equal(negative.found, '0');
  const partial = groundTruthProgress({ status: 'partially_assessed', defect_count: 4, assessed_defect_count: 2, discovered_defect_count: 1, discovery_rate: 0.25 });
  assert.equal(partial.label, '25%');
  assert.equal(partial.detail, '2 of 4 defects assessed');
});

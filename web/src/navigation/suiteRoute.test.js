import test from 'node:test';
import assert from 'node:assert/strict';
import { CASE_TABS, readSuiteRoute, suiteRouteHref } from './suiteRoute.js';

test('timing deep link restores the historical attempt after reopening', () => {
  const item = { agent_id: 'alpha', case_index: 0, attempts: [{ attempt_id: 'old' }, { attempt_id: 'new' }] };
  const href = suiteRouteHref(item, 'timing', { pathname: '/suite/test/', search: '' }, 'old');
  const route = readSuiteRoute([item], href.slice(href.indexOf('#')));
  assert.equal(route.tab, 'timing');
  assert.equal(route.attemptId, 'old');
});

const cases = [{ agent_id: 'alpha', case_index: 0 }, { agent_id: 'alpha', case_index: 1 }];

test('Agent introduction has a distinct shareable route including before Cases exist', () => {
  assert.deepEqual(readSuiteRoute(cases, '#agent=alpha'), { item: null, agent: 'alpha', tab: 'overview' });
  assert.deepEqual(readSuiteRoute([], '#agent=alpha', ['alpha']), { item: null, agent: 'alpha', tab: 'overview' });
  assert.deepEqual(readSuiteRoute(cases, '#agent=missing'), { item: null, tab: 'overview' });
  assert.equal(suiteRouteHref({ agent_id: 'alpha' }, 'overview', { pathname: '/suite/one/', search: '' }), '/suite/one/#agent=alpha');
});

test('Suite route distinguishes the overview from an exact Case', () => {
  assert.deepEqual(readSuiteRoute(cases, ''), { item: null, tab: 'overview' });
  assert.deepEqual(readSuiteRoute(cases, '#agent=alpha&case=1&tab=judge'), { item: cases[1], tab: 'judge' });
  assert.deepEqual(readSuiteRoute(cases, '#agent=missing&case=1&tab=unknown'), { item: null, tab: 'overview' });
});

test('Suite route creates a shareable Case URL without changing the base path', () => {
  const location = { pathname: '/suite/suite-one/', search: '?mode=local' };
  assert.equal(suiteRouteHref(null, 'overview', location), '/suite/suite-one/?mode=local');
  assert.equal(suiteRouteHref(cases[0], 'trace', location), '/suite/suite-one/?mode=local#agent=alpha&case=0&tab=timing');
});

test('Replay follows Timing and has a shareable Case route', () => {
  assert.equal(CASE_TABS[CASE_TABS.indexOf('timing') + 1], 'replay');
  const href = suiteRouteHref(cases[0], 'replay', { pathname: '/suite/one/', search: '' });
  assert.equal(readSuiteRoute(cases, href.slice(href.indexOf('#'))).tab, 'replay');
});

test('Judge leads Case navigation, Timing includes Trace, and existing JSON links still work', () => {
  assert.deepEqual(CASE_TABS, ['judge', 'overview', 'timing', 'replay', 'conversation', 'generation', 'tools', 'json']);
  const item = { agent_id: 'alpha', case_index: 0 };
  for (const tab of ['replay', 'generation', 'json']) {
    const href = suiteRouteHref(item, tab, { pathname: '/suite/one/', search: '?resultRun=run1&resultFile=evaluation%2Fcase.json' });
    assert.equal(readSuiteRoute([item], href.slice(href.indexOf('#'))).tab, tab);
    assert.ok(href.includes('resultFile=evaluation%2Fcase.json'));
  }
});

test('new Case links open Judge while explicit Overview and legacy Trace bookmarks still work', () => {
  const item = { ...cases[0], attempts: [{ attempt_id: 'old' }] };
  assert.equal(readSuiteRoute([item], '#agent=alpha&case=0').tab, 'judge');
  assert.equal(readSuiteRoute([item], '#agent=alpha&case=0&tab=overview').tab, 'overview');
  assert.deepEqual(readSuiteRoute([item], '#agent=alpha&case=0&tab=trace&attempt=old'), { item, tab: 'timing', attemptId: 'old' });
});

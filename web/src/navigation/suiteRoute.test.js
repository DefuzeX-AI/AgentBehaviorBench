import test from 'node:test';
import assert from 'node:assert/strict';
import { readSuiteRoute, suiteRouteHref } from './suiteRoute.js';

const cases = [{ agent_id: 'alpha', case_index: 0 }, { agent_id: 'alpha', case_index: 1 }];

test('Suite route distinguishes the overview from an exact Case', () => {
  assert.deepEqual(readSuiteRoute(cases, ''), { item: null, tab: 'overview' });
  assert.deepEqual(readSuiteRoute(cases, '#agent=alpha&case=1&tab=judge'), { item: cases[1], tab: 'judge' });
  assert.deepEqual(readSuiteRoute(cases, '#agent=missing&case=1&tab=unknown'), { item: null, tab: 'overview' });
});

test('Suite route creates a shareable Case URL without changing the base path', () => {
  const location = { pathname: '/suite/suite-one/', search: '?mode=local' };
  assert.equal(suiteRouteHref(null, 'overview', location), '/suite/suite-one/?mode=local');
  assert.equal(suiteRouteHref(cases[0], 'trace', location), '/suite/suite-one/?mode=local#agent=alpha&case=0&tab=trace');
});

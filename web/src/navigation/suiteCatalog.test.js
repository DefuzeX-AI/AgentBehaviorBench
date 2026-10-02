import test from 'node:test';
import assert from 'node:assert/strict';
import { suiteCatalogMatches, suiteCatalogRows, suiteEndpoint } from './suiteCatalog.js';

test('catalog keeps every Suite and updates only the selected snapshot', () => {
  const catalog = { suites: [{ suite_id: 'new', counts: { completed: 0 } }, { suite_id: 'old', counts: { completed: 1 } }] };
  const rows = suiteCatalogRows(catalog, { suite_id: 'new', counts: { completed: 2 }, jobs: [{ agent_id: 'agent' }] });
  assert.deepEqual(rows.map(suite => suite.suite_id), ['new', 'old']);
  assert.equal(rows[0].counts.completed, 2);
  assert.equal(rows[1].counts.completed, 1);
  assert.equal(catalog.suites[0].counts.completed, 0);
});

test('selected new Suite remains visible before the next catalog poll', () => {
  assert.deepEqual(suiteCatalogRows({ suites: [{ suite_id: 'old' }] }, { suite_id: 'new' }).map(row => row.suite_id), ['new', 'old']);
  assert.equal(suiteCatalogMatches({ suite_id: 'new', origin_suite_id: 'old', agent_ids: ['react-agent'] }, 'REACT'), true);
  assert.equal(suiteCatalogMatches({ suite_id: 'new', origin_suite_id: 'old' }, 'old'), true);
});

test('deep links select their Suite endpoint and root retains the default', () => {
  assert.equal(suiteEndpoint('/suite/suite_second/', '/api/suites/first/result'), '/api/suites/suite_second/result');
  assert.equal(suiteEndpoint('/', '/api/suites/first/result'), '/api/suites/first/result');
});

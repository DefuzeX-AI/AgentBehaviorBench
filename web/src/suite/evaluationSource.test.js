import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluationSourceView } from './evaluationSource.js';

test('saved SDK names display independently of the evaluated Agent', () => {
  assert.equal(evaluationSourceView({ status: 'recorded', sdks: ['kuma'] }).label, 'KUMA');
  assert.equal(evaluationSourceView({ status: 'recorded', sdks: ['local'] }).label, 'Local');
  assert.equal(evaluationSourceView({ status: 'recorded', sdks: ['custom_judge'] }).label, 'custom_judge');
  assert.equal(evaluationSourceView().label, 'Not recorded');
  assert.equal(evaluationSourceView({ status: 'not_recorded', provider_modes: ['unknown-engine'] }).label, 'Not recorded');
});

test('mixed and incomplete historical evidence is visible', () => {
  const mixed = evaluationSourceView({ status: 'mixed', sdks: ['kuma', 'local'], configured_sdk: 'kuma', provider_modes: ['local-container'] });
  assert.equal(mixed.label, 'Mixed');
  assert.match(mixed.description, /KUMA, Local/);
  assert.match(mixed.description, /Saved SDK selection: KUMA/);
  assert.match(mixed.description, /Recorded modes: local-container/);
  const partial = evaluationSourceView({ status: 'partial', sdks: ['local'] });
  assert.equal(partial.label, 'Local · partial');
  assert.match(partial.description, /Some Cases do not record/);
});

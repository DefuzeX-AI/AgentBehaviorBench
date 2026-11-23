import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { otelSpans } from './otel.js';
import { traceTree } from '../src/otel/tree.js';
import { evaluation } from './evaluation.js';
import { eventPage } from './events.js';

test('raw events page beyond 20 MiB without truncating individual payloads', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-events-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'run'));
  const body = 'Unicode-café\u2028'.repeat(4000000);
  await writeFile(path.join(root,'run/network.jsonl'), JSON.stringify({event:'large',data:body})+'\n'+JSON.stringify({event:'last'})+'\n');
  const first = await eventPage(root,'run',0,1);
  assert.equal(first.events[0].raw.data,body);
  assert.equal((await eventPage(root,'run',first.next,1)).events[0].raw.event,'last');
  await assert.rejects(eventPage(root,'../run'));
});

test('evaluation artifacts use the run and reject symlinks', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-evaluation-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const base = path.join(root, 'run/evaluation');
  const output = path.join(base, 'inputs/0001');
  await mkdir(output, { recursive: true });
  await writeFile(path.join(base, 'manifest.json'), JSON.stringify({judge:'received'}));
  await writeFile(path.join(output, 'input.json'), JSON.stringify({payload:'original SDK input'}));
  assert.equal((await evaluation(root,'run')).inputs[0].input.payload,'original SDK input');
  await writeFile(path.join(root,'secret.json'),'{}');
  await symlink(path.join(root,'secret.json'),path.join(base,'case.json'));
  await assert.rejects(evaluation(root,'run'));
});

test('OTel index lists only Agent-exported spans and blocks escapes', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-otel-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const step = path.join(root, 'run/steps/0001');
  const agent = path.join(root, 'run/otel');
  await mkdir(step, { recursive: true });
  await mkdir(agent, { recursive: true });
  // Step-level span files written by older runs are not Agent telemetry.
  await writeFile(path.join(step, 'otel.jsonl'), JSON.stringify({source:'otel', event:'span', data:{span_id:'0123456789abcdef', trace_id:'old'}})+'\n');
  assert.deepEqual((await otelSpans(root,'run')).spans, []);
  const span = {traceId:'ab'.repeat(16), spanId:'cd'.repeat(8), name:'chat', startTimeUnixNano:'1', endTimeUnixNano:'2',
    attributes:[{key:'gen_ai.operation.name', value:{stringValue:'chat'}}]};
  await writeFile(path.join(agent, 'status.json'), JSON.stringify({status:'received', span_count:1, record_count:1}));
  await writeFile(path.join(agent, 'spans.jsonl'), JSON.stringify({origin:'agent_native', scope:{}, resource:{}, span})+'\n');
  const result = await otelSpans(root,'run');
  assert.equal(result.spans.length,1);
  assert.equal(result.spans[0].origin,'agent_native');
  assert.equal(result.spans[0].attributes['gen_ai.operation.name'],'chat');
  assert.deepEqual(result.statuses.map(s => s.invocation), ['Agent']);
  await assert.rejects(otelSpans(root,'../escape'));
});

test('OTel tree keeps parallel siblings, separates traces and tolerates cycles', () => {
  const spans=[{trace_id:'a',span_id:'root'}, {trace_id:'a',span_id:'1',parent_span_id:'root'},
    {trace_id:'a',span_id:'2',parent_span_id:'root'}, {trace_id:'b',span_id:'root'}];
  const roots=traceTree(spans);
  assert.equal(roots.length,2); assert.equal(roots[0].children.length,2);
  assert.equal(traceTree([{trace_id:'a',span_id:'1',parent_span_id:'1'}]).length,1);
});

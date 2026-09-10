import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { otelSpans, otelPayload } from './otel.js';
import { traceTree } from '../src/otel/tree.js';
import { evaluation } from './evaluation.js';
import { eventPage } from './events.js';

test('raw events page beyond 20 MiB without truncating individual payloads', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-events-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'run'));
  const body = '中文\u2028'.repeat(4000000);
  await writeFile(path.join(root,'run/network.jsonl'), JSON.stringify({event:'large',data:body})+'\n'+JSON.stringify({event:'last'})+'\n');
  const first = await eventPage(root,'run',0,1);
  assert.equal(first.events[0].raw.data,body);
  assert.equal((await eventPage(root,'run',first.next,1)).events[0].raw.event,'last');
  await assert.rejects(eventPage(root,'../run'));
});

test('evaluation artifacts and nested OTel use the same run and reject symlinks', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-evaluation-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const base = path.join(root, 'run/evaluation');
  const output = path.join(base, 'inputs/0001');
  await mkdir(output, { recursive: true });
  await writeFile(path.join(base, 'manifest.json'), JSON.stringify({judge:'received'}));
  await writeFile(path.join(output, 'input.json'), JSON.stringify({payload:'SDK 原文'}));
  await writeFile(path.join(output, 'otel.jsonl'), JSON.stringify({source:'otel',event:'span',data:{span_id:'0123456789abcdef',attributes:{'abb.output_ref':'body.json'}}})+'\n');
  await writeFile(path.join(output, 'body.json'), JSON.stringify('完整报告'));
  assert.equal((await evaluation(root,'run')).inputs[0].input.payload,'SDK 原文');
  assert.equal(await otelPayload(root,'run','0123456789abcdef','output'),'完整报告');
  await writeFile(path.join(root,'secret.json'),'{}');
  await symlink(path.join(root,'secret.json'),path.join(base,'case.json'));
  await assert.rejects(evaluation(root,'run'));
});

test('OTel index does not load large payload; detail reads it completely and blocks escapes', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-otel-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const output = path.join(root, 'run/invocation-a/output');
  await mkdir(path.join(output, 'otel-payloads'), { recursive: true });
  const span = {span_id:'0123456789abcdef', trace_id:'trace', name:'原始执行', attributes:{'abb.output_ref':'otel-payloads/output.json'}};
  await writeFile(path.join(output, 'otel.jsonl'), JSON.stringify({source:'otel', event:'span', data:span})+'\n');
  const body = '中文\u2028<script>not HTML</script>'.repeat(800000);
  await writeFile(path.join(output, 'otel-payloads/output.json'), JSON.stringify(body));
  assert.equal((await otelSpans(root,'run')).spans.length,1);
  assert.equal(await otelPayload(root,'run',span.span_id,'output'),body);
  await assert.rejects(otelSpans(root,'../escape'));
  await writeFile(path.join(root,'secret'),'"secret"');
  await symlink(path.join(root,'secret'),path.join(output,'otel-payloads/escape.json'));
  span.attributes['abb.output_ref']='otel-payloads/escape.json';
  await writeFile(path.join(output,'otel.jsonl'),JSON.stringify({source:'otel',event:'span',data:span})+'\n');
  await assert.rejects(otelPayload(root,'run',span.span_id,'output'));
});

test('OTel tree keeps parallel siblings, separates traces and tolerates cycles', () => {
  const spans=[{trace_id:'a',span_id:'root'}, {trace_id:'a',span_id:'1',parent_span_id:'root'},
    {trace_id:'a',span_id:'2',parent_span_id:'root'}, {trace_id:'b',span_id:'root'}];
  const roots=traceTree(spans);
  assert.equal(roots.length,2); assert.equal(roots[0].children.length,2);
  assert.equal(traceTree([{trace_id:'a',span_id:'1',parent_span_id:'1'}]).length,1);
});

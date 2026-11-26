import { pathToFileURL } from 'node:url';
import { randomUUID } from 'node:crypto';

const root = '/opt/agent/agent';
const emit = (event) => process.stdout.write(JSON.stringify(event) + '\n');
console.log = (...args) => console.error(...args);
let input = '';
for await (const chunk of process.stdin) input += chunk.toString();
const request = JSON.parse(input);
const { buildProtocolClient } = await import(pathToFileURL(root + '/apps/cli/dist/protocol-repl.js'));
const { ASSISTANT_ID } = await import(pathToFileURL(root + '/packages/core/dist/index.js'));
const client = buildProtocolClient('http://127.0.0.1:18080', process.env.PIZZA_API_TOKEN);
const thread = client.threads.stream(request.threadId || randomUUID(), { assistantId: ASSISTANT_ID });
let sub;
process.once('SIGTERM', async () => {
  try { await thread.stop(); } finally { await thread.close(); process.exit(143); }
});
try {
  await thread.submitRun({ input: { messages: [{ role: 'user', content: request.text }] },
    config: { configurable: { thread_id: request.threadId, model: process.env.PIZZA_MODEL } } });
  sub = await thread.subscribe(['messages', 'tools', 'lifecycle', 'input']);
  let completed = false;
  for await (const event of sub) {
    emit({ type: 'native_event', event });
    const data = event.params?.data;
    if (event.method === 'messages' && data?.event === 'content-block-delta' && data.delta?.type === 'text-delta') {
      emit({ type: 'token', content: data.delta.text || '' });
    }
    if (event.method === 'input.requested') throw new Error('Native run requires human approval');
    if (event.method === 'messages' && data?.event === 'error') throw new Error(data.message || 'Native message error');
    if (event.method === 'lifecycle' && event.params.namespace.length === 0) {
      if (data?.event === 'failed') throw new Error(data.error || 'Native run failed');
      if (data?.event === 'completed') { completed = true; break; }
    }
  }
  if (!completed) throw new Error('Native stream ended without completing');
} catch (error) {
  emit({ type: 'error', error: String(error) });
  process.exitCode = 1;
} finally {
  await sub?.unsubscribe().catch(() => {});
  await thread.close().catch(() => {});
}

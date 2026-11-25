import { pathToFileURL } from 'node:url';

const emit = (event: unknown) => process.stdout.write(JSON.stringify(event) + '\n');
console.log = (...args: unknown[]) => console.error(...args);
let input = '';
for await (const chunk of process.stdin) input += chunk.toString();
const request = JSON.parse(input);
const native = '/opt/agent/agent/apps/server/src';
try {
  const { default: models } = await import(pathToFileURL(native + '/model.json').href, { with: { type: 'json' } });
  models.push({
    provider: 'abb', type: 'openai', apiMode: 'openai-completions',
    baseURL: process.env.ABB_AGENT_MODEL_BASE_URL,
    apiKey: process.env.ABB_AGENT_MODEL_API_KEY,
    models: [{ name: process.env.ABB_AGENT_MODEL }],
  });
  const { SearchChat } = await import(pathToFileURL(native + '/core/agent/search/index.ts').href);
  const agent = new SearchChat({ provider: 'abb', model: process.env.ABB_AGENT_MODEL });
  let completed = false;
  await agent.chat({ messages: [...request.history, { role: 'user', content: request.text }] },
    (message: any, done?: boolean) => {
      if (message) {
        emit({ type: 'native_event', message });
        if (message.role === 'assistant' && message.content) emit({ type: 'token', content: message.content });
      }
      if (done) completed = true;
    });
  if (!completed) throw new Error('The native SearchChat stream did not complete');
} catch (error) {
  emit({ type: 'error', error: String(error) });
  process.exitCode = 1;
}

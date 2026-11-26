// Run the original Electron chat handler with a real Electron store and WebContents.
const { createRequire } = require('node:module');
const nativeRequire = createRequire('/opt/agent/agent/electron/package.json');
const { app, BrowserWindow } = nativeRequire('electron');
const { randomUUID } = require('node:crypto');
console.log = (...values) => console.error(...values);

async function main() {
  app.setName('Specif AI');
  await app.whenReady();
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const { text } = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  const Store = nativeRequire('electron-store');
  const { store } = nativeRequire('./build/services/store/index.js');
  store.initialize(new Store());
  store.set('llmConfig', {
    activeProvider: 'openrouter', isDefault: false,
    providerConfigs: { openrouter: { config: {
      model: process.env.ABB_AGENT_MODEL,
      baseUrl: process.env.ABB_AGENT_MODEL_BASE_URL,
      apiKey: process.env.ABB_AGENT_MODEL_API_KEY,
    } } },
  });
  const window = new BrowserWindow({ show: false });
  const { chatWithAI } = nativeRequire('./build/api/core/chat.js');
  const state = await chatWithAI({ sender: window.webContents }, {
    requestId: randomUUID(), requirementAbbr: 'BRD',
    project: { name: '', description: '' },
    requirement: { title: '', description: '' },
    chatHistory: [{ type: 'user', content: [{ type: 'text', text }] }],
  });
  const values = state.values || state;
  if (values.structuredResponse?.blocked) {
    throw new Error(`Native Specifai blocked the request: ${values.structuredResponse.blockedReason}`);
  }
  const message = [...(values.messages || [])].reverse().find(m =>
    (m._getType?.() === 'ai' || m.type === 'ai') && m.content);
  const reply = typeof message?.content === 'string' ? message.content :
    (message?.content || []).filter(b => b.type === 'text').map(b => b.text).join('');
  if (!reply) throw new Error('Native Specifai returned no assistant reply');
  process.stdout.write('ABB_RESULT ' + JSON.stringify({ success: true, output: reply, state }) + '\n');
  window.destroy();
  app.exit(0);
}
main().catch(error => { console.error(error); app.exit(1); });

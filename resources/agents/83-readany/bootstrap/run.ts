// Transport only: all reasoning, routing, prompts and tools remain upstream.
console.log = (...values) => console.error(...values);
let request = "";
for await (const chunk of process.stdin) request += chunk.toString();
const input = JSON.parse(request);
const core = "/opt/agent/agent/packages/core/src";
const { setPlatformService } = await import(`${core}/services/platform.ts`);
const { createNodePlatformService } = await import("/opt/agent/agent/packages/cli/src/platform/node-platform.ts");
setPlatformService(createNodePlatformService(process.env));
const { initDatabase, closeDB, closeLocalDB } = await import(`${core}/db/database.ts`);
await initDatabase();
try {
  const { streamReadingAgent } = await import(`${core}/ai/agents/reading-agent.ts`);
  const { getAvailableTools } = await import(`${core}/ai/tools/index.ts`);
  const { getBuiltinSkills } = await import(`${core}/ai/skills/builtin-skills.ts`);
  const { useSettingsStore } = await import(`${core}/stores/settings-store.ts`);
  const endpoint = {id: "abb", name: "ABB runtime", provider: "custom",
    apiKey: process.env.ABB_AGENT_MODEL_API_KEY,
    baseUrl: process.env.ABB_AGENT_MODEL_BASE_URL,
    models: [process.env.ABB_AGENT_MODEL], modelsFetched: false};
  const aiConfig = {...useSettingsStore.getState().aiConfig,
    endpoints: [endpoint], activeEndpointId: "abb", activeModel: process.env.ABB_AGENT_MODEL};
  for await (const event of streamReadingAgent({aiConfig, book: null,
      semanticContext: null, enabledSkills: getBuiltinSkills().filter(s => s.enabled),
      isVectorized: false, getAvailableTools}, input.text, input.history)) {
    process.stdout.write(JSON.stringify(event)+"\n");
  }
} finally {
  await closeDB();
  await closeLocalDB();
}

// Keep diagnostics off native ACP stdout; the SDK retains its original stream.
import { format } from 'node:util';
for (const name of ['log', 'info', 'debug']) {
  console[name] = (...args) => process.stderr.write(`${format(...args)}\n`);
}
const root = new URL('../agent/', import.meta.url);
const db = await import(new URL('packages/gateway/dist/db-exports.js', root));
await db.initializeAdapter();
await db.initializeSettingsRepo();
await db.initializeConfigServicesRepo();
await db.seedConfigServices();
await db.initializePluginsRepo();
await db.initializeLocalProvidersRepo();
// The ACP CLI initializes repositories but omits gateway capability singletons.
// Install the original concrete services through their native setters, as the
// gateway server does; do not substitute implementations or change tool groups.
const core = await import(new URL('packages/core/dist/services/index.js', root));
const gateway = await import(new URL('packages/gateway/dist/index.js', root));
core.initServiceRegistry();
core.setConfigCenter(gateway.gatewayConfigCenter);
const router = await import(new URL('packages/gateway/dist/services/llm/router.js', root));
router.installLLMRouter();
const permissions = await import(new URL('packages/gateway/dist/services/permission/gate.js', root));
permissions.installPermissionGate();
const embeddings = await import(new URL('packages/gateway/dist/services/embedding/service.js', root));
core.setEmbeddingService(embeddings.getEmbeddingService());
core.setDatabaseService(gateway.getCustomDataService());
core.setResourceService(gateway.createResourceServiceImpl());
core.setPluginService(await gateway.createPluginService());
core.setMemoryService(gateway.getMemoryService());
core.setGoalService(gateway.getGoalService());
core.setTriggerService(gateway.getTriggerService());
core.setPlanService(gateway.getPlanService());
core.setToolService(gateway.createToolService());
core.setProviderService(gateway.createProviderService());
core.setAuditService(gateway.createAuditService());
core.setWorkspaceService(gateway.createWorkspaceServiceImpl());
const settings = await import(new URL('packages/gateway/dist/config-exports.js', root));
await db.settingsRepo.set('api_key:abb-runtime', process.env.ABB_AGENT_MODEL_API_KEY);
await settings.setDefaultProvider('abb-runtime');
await settings.setDefaultModel(process.env.ABB_AGENT_MODEL);
process.argv = [process.execPath, new URL('packages/cli/dist/index.js', root).pathname, 'acp-serve'];
await import(new URL('packages/cli/dist/index.js', root));

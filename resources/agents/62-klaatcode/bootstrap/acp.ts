/** Model-selection bootstrap around the pinned native ACP implementation. */
import { AcpConnection } from "../agent/src/acp/connection.ts";
import { AcpAgent } from "../agent/src/acp/agent.ts";
import type { KlaatAIClient } from "../agent/src/api/client.ts";

const endpoint = {
  name: "ABB selected model",
  baseUrl: process.env.ABB_AGENT_MODEL_BASE_URL!,
  model: process.env.ABB_AGENT_MODEL!,
  apiKey: process.env.ABB_AGENT_MODEL_API_KEY!,
};
for (const value of Object.values(endpoint)) {
  if (!value?.trim()) throw new Error("Incomplete ABB model selection");
}

const connection = new AcpConnection(process.stdin, process.stdout);
const register = connection.onRequest.bind(connection);
let agent: AcpAgent;
connection.onRequest = (method, handler) => register(method, method !== "initialize" ? handler : async params => {
  const response = await handler(params);
  // Native ACP initialize creates the same KlaatAIClient as the TUI, but does
  // not expose /model. Set only that client's native custom-endpoint setting.
  // Its property name is pinned to the recorded upstream revision.
  const client = (agent as unknown as { client: KlaatAIClient | null }).client;
  if (!client || typeof client.setCustomEndpoint !== "function") {
    throw new Error("Pinned native ACP client contract changed");
  }
  client.setCustomEndpoint(endpoint);
  return response;
});
agent = new AcpAgent(connection);
process.stdin.resume();
process.stdin.on("end", () => process.exit(0));

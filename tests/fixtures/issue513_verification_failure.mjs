/** Offline ACP fixture, not a native Agent or live acceptance record. */
import { createInterface } from 'node:readline';

const send = (message) => process.stdout.write(JSON.stringify(message) + '\n');
for await (const frame of createInterface({ input: process.stdin })) {
  const message = JSON.parse(frame);
  if (message.method === 'initialize') {
    send({ jsonrpc: '2.0', id: message.id, result: {
      protocolVersion: message.params.protocolVersion, agentCapabilities: {},
      agentInfo: { name: 'offline-verification-failure-fixture', version: '1' },
      authMethods: [],
    } });
  } else if (message.method === 'session/new') {
    send({ jsonrpc: '2.0', id: message.id, result: { sessionId: 'offline-session' } });
  } else if (message.method === 'session/prompt') {
    send({ jsonrpc: '2.0', method: 'session/update', params: {
      sessionId: message.params.sessionId, update: { sessionUpdate: 'agent_message_chunk',
        content: { type: 'text', text: 'Native streamed text remains unchanged.' } },
    } });
    send({ jsonrpc: '2.0', id: message.id, error: {
      code: -32603, message: 'Internal error: Agent turn failed (verification_failed)', data: {
        failureType: 'verification_failed', modelId: 'offline-model',
        outputStarted: true, toolExecutionStarted: true, toolCallsCount: 18,
        taskFailure: { reason: 'No fresh verification PASS' },
      },
    } });
  }
}

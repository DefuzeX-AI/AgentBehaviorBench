// Invoke the published native benchmark entrypoint without replacing its graph or tools.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import {presentState} from './presentation.mjs';

const packageRoot = process.cwd();
const workspace = '/home/agent/workspace';
// Runtime data stays separate from the task workspace and its file evidence.
process.env.SCLAW_DATA_DIR = '/home/agent/.structureclaw';
process.env.DATABASE_URL = `file:${process.env.SCLAW_DATA_DIR}/data/structureclaw.db`;
fs.mkdirSync(process.env.SCLAW_DATA_DIR, { recursive: true });
fs.mkdirSync(workspace, { recursive: true });
const settingsFile = path.join(process.env.SCLAW_DATA_DIR, 'settings.json');
if (!fs.existsSync(settingsFile)) {
  fs.writeFileSync(settingsFile, JSON.stringify({
    agent: {workspaceRoot: workspace},
    analysis: {pythonBin: '/usr/local/bin/python'},
  }), {mode: 0o600});
}
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const input = request.input;
const moduleUrl = (relative) => pathToFileURL(path.join(packageRoot, 'dist/backend', relative)).href;
const {getAgentService} = await import(moduleUrl('agent-langgraph/agent-service.js'));
const {prisma} = await import(moduleUrl('utils/database.js'));
try {
  const service = getAgentService();
  let state;
  const chunks = [];
  if (request.resume) {
    for await (const chunk of service.resumeStream(input.conversationId, input.message)) {
      chunks.push(chunk);
    }
    const snapshot = await service.getConversationSessionSnapshot(input.conversationId);
    if (!snapshot) throw new Error('Native session snapshot unavailable after resume');
    state = snapshot.state;
  } else {
    state = await service.runFull(input);
  }
  fs.writeFileSync(process.argv[2], JSON.stringify(presentState(state, chunks)));
} finally {
  await prisma.$disconnect();
}

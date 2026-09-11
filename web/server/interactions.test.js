import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { interactionPage } from './interactions.js';

test('Vite serves the Python interaction contract with pagination and rejects escapes', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'abb-interactions-'));
  try {
    await mkdir(path.join(root, 'run'));
    await writeFile(path.join(root, 'run/network.jsonl'), Array.from({ length: 11 }, (_, i) => JSON.stringify({
      event: 'llm_request', timestamp: `2026-09-10T07:00:${String(i).padStart(2, '0')}Z`,
      data: { call_id: `call-${i}`, model: 'arbitrary-model', payload: { messages: [] } },
    })).join('\n'));
    const page = await interactionPage(root, 'run', { page: 2, page_size: 10 });
    assert.equal(page.total, 11); assert.equal(page.items.length, 1);
    const detail = await interactionPage(root, 'run', { id: page.items[0].id });
    assert.equal(detail.request.call_id, 'call-10');
    await assert.rejects(interactionPage(root, '../run', {}));
    await symlink(tmpdir(), path.join(root, 'escape'));
    await assert.rejects(interactionPage(root, 'escape', {}));
  } finally { await rm(root, { recursive: true, force: true }); }
});

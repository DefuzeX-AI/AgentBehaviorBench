import test from 'node:test';
import assert from 'node:assert/strict';
import { suiteProxySettings } from './suiteProxy.js';
import { createServer as createHttpServer } from 'node:http';
import { createServer as createViteServer } from 'vite';

test('unbound development retains read-only mode', () => {
  assert.equal(suiteProxySettings({}).proxy, undefined);
});
test('bound development injects exact Suite endpoint and proxies Python', () => {
  const settings = suiteProxySettings({ ABB_VIEWER_BACKEND: 'http://127.0.0.1:8888', ABB_SUITE_ID: 'suite_a' });
  assert.equal(settings.plugins[0].transformIndexHtml()[0].attrs.content, '/api/suites/suite_a/result');
  assert.equal(settings.proxy['/api'].target, 'http://127.0.0.1:8888');
});
test('proxy refuses remote targets and unsafe Suite IDs', () => {
  for (const backend of ['https://example.com', 'http://user:pass@localhost:8888', 'http://localhost:8888/arbitrary']) {
    assert.throws(() => suiteProxySettings({ ABB_VIEWER_BACKEND: backend, ABB_SUITE_ID: 'suite_a' }));
  }
  assert.throws(() => suiteProxySettings({ ABB_VIEWER_BACKEND: 'http://localhost:8888', ABB_SUITE_ID: '../other' }));
});

test('development proxy rejects foreign origins before forwarding accepted local commands', async () => {
  const seen = [];
  const backend = createHttpServer((request, response) => {
    seen.push({ url: request.url, origin: request.headers.origin, token: request.headers['x-abb-control-token'] });
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ status: 'accepted' }));
  });
  await new Promise(resolve => backend.listen(0, '127.0.0.1', resolve));
  const backendOrigin = `http://127.0.0.1:${backend.address().port}`;
  const settings = suiteProxySettings({ ABB_VIEWER_BACKEND: backendOrigin, ABB_SUITE_ID: 'suite_local' });
  const server = await createViteServer({ configFile: false, plugins: settings.plugins,
    server: { host: '127.0.0.1', port: 0, proxy: settings.proxy }, logLevel: 'silent' });
  try {
    await server.listen();
    const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
    const target = `${origin}/api/suites/suite_local/commands`;
    const denied = await fetch(target, { method: 'POST', headers: { Origin: 'https://foreign.example', 'Content-Type': 'application/json' }, body: '{}' });
    assert.equal(denied.status, 403);
    assert.equal(seen.length, 0);
    const accepted = await fetch(target, { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json', 'X-ABB-Control-Token': 'fixture-token' }, body: '{}' });
    assert.equal(accepted.status, 200);
    assert.deepEqual(seen, [{ url: '/api/suites/suite_local/commands', origin: backendOrigin, token: 'fixture-token' }]);
  } finally {
    await server.close();
    await new Promise(resolve => backend.close(resolve));
  }
});

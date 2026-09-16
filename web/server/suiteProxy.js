// Development uses the Python Suite API; it does not implement a second scheduler.
export function suiteProxySettings(environment = process.env) {
  const backend = environment.ABB_VIEWER_BACKEND;
  const suiteId = environment.ABB_SUITE_ID;
  if (!backend && !suiteId) return { plugins: [], proxy: undefined };
  if (!backend || !suiteId) throw new Error('Set ABB_VIEWER_BACKEND and ABB_SUITE_ID together.');
  const target = new URL(backend);
  if (target.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(target.hostname)
    || target.username || target.password || target.pathname !== '/' || target.search || target.hash) {
    throw new Error('ABB_VIEWER_BACKEND must be the HTTP origin of a local Python viewer.');
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(suiteId)) throw new Error('Invalid ABB_SUITE_ID.');
  const resultUrl = `/api/suites/${suiteId}/result`;
  function install(server) {
    server.middlewares.use((request, response, next) => {
      if (!request.url.startsWith('/api/')) return next();
      const ownOrigin = `http://${request.headers.host}`;
      if (!/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(request.headers.host || '')
        || (request.headers.origin && request.headers.origin !== ownOrigin)
        || request.headers['sec-fetch-site'] === 'cross-site') {
        response.writeHead(403, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify({ error: 'Only local same-origin requests are allowed.' }));
        return;
      }
      next();
    });
  }
  return {
    plugins: [{ name: 'abb-python-suite', configureServer: install, configurePreviewServer: install,
      transformIndexHtml: () => [{ tag: 'meta', attrs: { name: 'abb-result-api', content: resultUrl }, injectTo: 'head' }] }],
    proxy: { '/api': { target: target.origin, changeOrigin: true,
      configure(proxy) {
        proxy.on('proxyReq', (proxyRequest, request) => {
          // Original origin was validated above; Python sees its own local origin.
          if (request.headers.origin) proxyRequest.setHeader('Origin', target.origin);
        });
      },
    } },
  };
}

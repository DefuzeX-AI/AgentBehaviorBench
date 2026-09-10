import { readdir, readFile, realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { otelSpans, otelPayload } from './otel.js';
import { evaluation } from './evaluation.js';
import { eventPage } from './events.js';
import { interactionPage } from './interactions.js';

const MAX_BYTES = 20 * 1024 * 1024;
const validId = id => /^[a-zA-Z0-9_-]+$/.test(id);

async function contained(root, target) {
  const base = await realpath(root);
  const resolved = await realpath(target);
  if (!resolved.startsWith(base + path.sep)) throw new Error('路径越界');
  return resolved;
}

async function readBounded(file, max = MAX_BYTES) {
  const info = await stat(file);
  if (!info.isFile() || info.size > max) throw new Error('文件过大或不是普通文件');
  return readFile(file, 'utf8');
}

export async function listRuns(root) {
  let entries;
  try { entries = await readdir(root, { withFileTypes: true }); }
  catch (error) { if (error.code === 'ENOENT') return []; throw error; }
  const runs = await Promise.all(entries.filter(e => e.isDirectory() && validId(e.name)).map(async e => {
    try {
      const file = await contained(root, path.join(root, e.name, 'run.json'));
      const metadata = JSON.parse(await readBounded(file));
      const info = await stat(file);
      return { id: e.name, agent: String(metadata.agent_id || '未知 Agent'),
        status: String(metadata.status || 'unknown'), updated: info.mtime.toISOString() };
    } catch {
      return { id: e.name, agent: '未知 Agent', status: 'unavailable', updated: null };
    }
  }));
  return runs.sort((a, b) => (b.updated || '').localeCompare(a.updated || ''));
}

export async function readRun(root, id) {
  if (!validId(id)) throw new Error('无效任务编号');
  const directory = await contained(root, path.join(root, id));
  const entries = await readdir(directory, { withFileTypes: true });
  const candidates = ['network.jsonl', ...entries.filter(e => e.isDirectory() && e.name.startsWith('invocation-'))
    .map(e => `${e.name}/output/framework.jsonl`)];
  const files = [];
  const warnings = [];
  let remaining = MAX_BYTES;
  for (const name of candidates) {
    try {
      const file = await contained(directory, path.join(directory, name));
      const content = await readBounded(file, remaining);
      remaining -= Buffer.byteLength(content);
      files.push({ name, content });
    } catch (error) {
      if (error.code !== 'ENOENT') warnings.push(`${name}：无法读取（权限、路径或大小限制）`);
    }
  }
  if (!files.length) warnings.push('此任务尚无可读取的 trace 文件，可能未进入执行阶段。');
  return { id, files, warnings };
}

export function runsPlugin(root) {
  function install(server) {
    server.middlewares.use(async (req, res, next) => {
      const url = new URL(req.url, 'http://localhost');
      if (!url.pathname.startsWith('/api/observe/')) return next();
      res.setHeader('Content-Type', 'application/json; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store');
      const reply = (status, value) => { res.statusCode = status; res.end(JSON.stringify(value)); };
      // Local, same-origin read-only API. Never enable CORS or arbitrary file paths.
      if (!/^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(req.headers.host || '') ||
          (req.headers.origin && req.headers.origin !== `http://${req.headers.host}`) ||
          req.headers['sec-fetch-site'] === 'cross-site') return reply(403, { error: '仅允许本地同源访问' });
      if (req.method !== 'GET') return reply(405, { error: '仅支持读取' });
      try {
        const interactions = /^\/api\/observe\/runs\/([a-zA-Z0-9_-]+)\/interactions$/.exec(url.pathname);
        if (interactions) {
          const controller = new AbortController();
          res.on('close', () => { if (!res.writableEnded) controller.abort(); });
          return reply(200, await interactionPage(root, interactions[1], Object.fromEntries(url.searchParams), controller.signal));
        }
        const eventMatch = /^\/api\/observe\/runs\/([a-zA-Z0-9_-]+)\/events$/.exec(url.pathname);
        if (eventMatch) return reply(200, await eventPage(root, eventMatch[1], Number(url.searchParams.get('offset') || 0)));
        const evaluated = /^\/api\/observe\/runs\/([a-zA-Z0-9_-]+)\/evaluation$/.exec(url.pathname);
        if (evaluated) return reply(200, await evaluation(root, evaluated[1]));
        const otel = /^\/api\/observe\/runs\/([a-zA-Z0-9_-]+)\/otel(?:\/([0-9a-f]{16})\/payload\/(input|output|error|metadata|events))?$/.exec(url.pathname);
        if (otel) return reply(200, otel[2]
          ? { payload: await otelPayload(root, otel[1], otel[2], otel[3]) }
          : await otelSpans(root, otel[1]));
        if (url.pathname === '/api/observe/runs') return reply(200, { runs: await listRuns(root) });
        const match = /^\/api\/observe\/runs\/([a-zA-Z0-9_-]+)$/.exec(url.pathname);
        if (match) return reply(200, await readRun(root, match[1]));
        return reply(404, { error: '任务不存在' });
      } catch { return reply(404, { error: '任务不存在或无法读取，请刷新列表' }); }
    });
  }
  return { name: 'abb-local-runs', configureServer: install, configurePreviewServer: install };
}

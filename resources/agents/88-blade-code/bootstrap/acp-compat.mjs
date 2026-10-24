/** Adapt ACP transport boundaries without changing native tools or verification. */
import { spawn } from 'node:child_process';
import { lstatSync, realpathSync, statSync } from 'node:fs';
import path from 'node:path';
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';

function parse(frame) {
  try { return JSON.parse(frame); } catch { return null; }
}

function inside(root, target) {
  const relative = path.relative(root, target);
  return relative === '' || (!path.isAbsolute(relative)
    && relative !== '..' && !relative.startsWith('..' + path.sep));
}

/** Verify ENOENT against the real shared workspace, including existing symlinks. */
export function missingWorkspaceFile(workspace, requestedPath) {
  if (typeof requestedPath !== 'string' || !path.isAbsolute(requestedPath)
      || requestedPath.includes('\0')) return false;
  try {
    const root = realpathSync(workspace);
    const target = path.resolve(root, requestedPath);
    if (!inside(root, target)) return false;
    try { statSync(target); return false; } catch (error) {
      if (error.code !== 'ENOENT') return false;
    }
    let ancestor = target;
    while (true) {
      try {
        lstatSync(ancestor);
      } catch (error) {
        if (error.code !== 'ENOENT') return false;
        const parent = path.dirname(ancestor);
        if (parent === ancestor) return false;
        ancestor = parent;
        continue;
      }
      // Do not walk past an existing but broken symlink: its destination has
      // not been proven to belong to this workspace.
      return inside(root, realpathSync(ancestor));
    }
  } catch { return false; }
}

export function createCompatibility(workspace) {
  const reads = new Map();
  const prompts = new Map();
  return {
    fromAgent(frame) {
      const message = parse(frame);
      if (!message || typeof message !== 'object') return frame;
      if (!message.method && prompts.has(message.id)) {
        const sessionId = prompts.get(message.id);
        prompts.delete(message.id);
        // Blade's native ACP Session throws this typed error after its own
        // verification gate fails. ABB accepts an explicit refusal, but rejects
        // an RPC exception before a Judge can inspect the existing evidence.
        // Keep the gate enabled, preserve already-streamed native text, and
        // disclose the failure as an adapter diagnostic rather than a PASS.
        if (message.jsonrpc === '2.0' && !Object.hasOwn(message, 'result')
            && message.error?.code === -32603
            && message.error?.data?.failureType === 'verification_failed'
            && message.error.message === 'Agent turn failed (verification_failed)') {
          const diagnostic = { jsonrpc: '2.0', method: 'session/update', params: {
            sessionId, update: { sessionUpdate: 'agent_message_chunk', content: {
              type: 'text', text: '\n[ABB adapter diagnostic: verification_failed] '
                + 'Blade Code did not obtain a verified completion. Any preceding '
                + 'Agent text remains unverified; this is not a verification PASS. '
                + 'The native verification gate remains enabled. The original '
                + 'ACP error is retained in the prompt response metadata.\n',
            } },
          } };
          const response = { jsonrpc: '2.0', id: message.id, result: {
            stopReason: 'refusal', _meta: { 'abb/verificationFailure': {
              status: 'failed', nativeVerificationEnabled: true,
              nativeError: message.error,
            } },
          } };
          return JSON.stringify(diagnostic) + '\n' + JSON.stringify(response);
        }
      }
      if (message.method === 'fs/read_text_file'
          && ['string', 'number'].includes(typeof message.id)
          && typeof message.params?.path === 'string') {
        reads.set(message.id, message.params.path);
      }
      if (message.method === 'terminal/create'
          && typeof message.params?.command === 'string'
          && (message.params.args === undefined
            || (Array.isArray(message.params.args) && message.params.args.length === 0))) {
        return JSON.stringify({ ...message, params: { ...message.params,
          command: '/bin/bash', args: ['-c', message.params.command] } });
      }
      return frame;
    },
    fromClient(frame) {
      const message = parse(frame);
      if (message?.method === 'session/prompt'
          && ['string', 'number'].includes(typeof message.id)
          && typeof message.params?.sessionId === 'string'
          && message.params.sessionId.trim()) {
        prompts.set(message.id, message.params.sessionId);
        return frame;
      }
      if (!message || typeof message !== 'object' || message.method || !reads.has(message.id)) return frame;
      const requestedPath = reads.get(message.id);
      reads.delete(message.id);
      // ABB's adapter serializes FileNotFoundError as an internal error. Blade
      // expects ACP ResourceNotFound before creating a new file. Only normalize
      // when the co-located filesystem independently confirms that absence.
      if (message.error?.code === -32603 && missingWorkspaceFile(workspace, requestedPath)) {
        return JSON.stringify({ ...message, error: { ...message.error,
          code: -32002, message: 'File not found' } });
      }
      return frame;
    },
  };
}

function main() {
  const [command, ...args] = process.argv.slice(2);
  if (!command) throw new Error('Native ACP command is required');
  const compatibility = createCompatibility(process.cwd());
  const native = spawn(command, args, { stdio: ['pipe', 'pipe', 'pipe'] });
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const output = createInterface({ input: native.stdout, crlfDelay: Infinity });
  native.stderr.pipe(process.stderr);
  input.on('line', (frame) => {
    if (!native.stdin.write(compatibility.fromClient(frame) + '\n')) input.pause();
  });
  output.on('line', (frame) => {
    if (!process.stdout.write(compatibility.fromAgent(frame) + '\n')) output.pause();
  });
  native.stdin.on('drain', () => input.resume());
  process.stdout.on('drain', () => output.resume());
  native.stdin.on('error', (error) => {
    if (error.code !== 'EPIPE') process.stderr.write('Native ACP input failed\n');
    input.close();
    process.stdin.pause();
  });
  input.on('close', () => native.stdin.end());
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => native.kill(signal));
  }
  native.on('error', () => {
    process.stderr.write('Could not start the native ACP process\n');
    input.close();
    process.stdin.pause();
    process.exitCode = 1;
  });
  native.on('close', (code, signal) => {
    input.close();
    process.stdin.pause();
    process.exitCode = code ?? (signal ? 1 : 0);
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();

// Patch the compiled ACP bridge so a "final" chat event flushes any reply text
// that the throttled "delta" events have not yet delivered.
//
// The Gateway rate-limits chat deltas to one every 150 ms and always sends the
// complete text in the "final" event, but the ACP translator only forwarded
// text from "delta" events and dropped the "final" payload. For a fast model
// stream that means the reply is cut off at the last delta window. This rewrites
// the final branch to flush the remaining text before ending the turn.
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const dist = join(dirname(fileURLToPath(import.meta.url)), "dist");

const before =
  'if (state === "final") {\n' +
  '\t\t\tthis.finishPrompt(pending.sessionId, pending, "end_turn");\n' +
  '\t\t\treturn;\n' +
  '\t\t}';

const after =
  'if (state === "final") {\n' +
  '\t\t\tif (messageData) await this.handleDeltaEvent(pending.sessionId, messageData);\n' +
  '\t\t\tthis.finishPrompt(pending.sessionId, pending, "end_turn");\n' +
  '\t\t\treturn;\n' +
  '\t\t}';

let patched = 0;
let failed = 0;

for (const name of readdirSync(dist)) {
  if (!/^acp-cli-.*\.js$/.test(name)) continue;
  const path = join(dist, name);
  const text = readFileSync(path, "utf8");
  if (text.includes(after)) {
    continue; // already patched
  }
  if (!text.includes(before)) {
    console.error(`patch-acp-final: target string not found in ${name}`);
    failed += 1;
    continue;
  }
  writeFileSync(path, text.replace(before, after), "utf8");
  patched += 1;
}

console.error(`patch-acp-final: patched ${patched} file(s), failed ${failed}`);
if (failed) process.exit(1);

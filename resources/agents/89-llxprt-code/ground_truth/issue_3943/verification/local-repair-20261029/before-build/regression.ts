import { ShellToolInvocation } from "./source/packages/tools/src/tools/shell.ts";
import { getShellToolDescription } from "./source/packages/tools/src/tools/shell-helpers.ts";
const instance=Object.create(ShellToolInvocation.prototype);
instance.params={command:"python3 marker.py"};
instance.host={getDebugMode:()=>false};
const out=instance.formatNormalOutput({exitCode:0,signal:null,pid:1},"to-stdout\nto-stderr","python3 marker.py",[],null).llmContent;
const desc=getShellToolDescription();
console.log(JSON.stringify({out,description:desc}));
if (!out.includes("Output (stdout and stderr combined):") || out.includes("Stderr: (empty)") || !desc.includes("stream attribution is unavailable")) process.exit(1);

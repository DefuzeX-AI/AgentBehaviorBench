# ACP integration contract

The runtime adapter is `acp`, transport `stdio`. adapter.command is a nonempty argv
array with a verified executable and arguments, not a shell command. adapter.cwd
is an absolute writable container workspace path. BBA launches the process in the
Case container and performs initialize -> optional authenticate -> session/new ->
session/prompt. One Case attempt owns one session; later inputs reuse it.

No graph config, Python binding, or in_process mode is valid here. Text input goes
directly to ACP; optional input_key selects one string in a structured task. Do not
replay history or add a synthetic adapter LLM. Authentication must be noninteractive:
use declared environment keys or an explicitly advertised auth_method. Never put
credentials in command arguments. permission_policy is deny or allow_once.

The image must supply the selected CLI, Node/runtime version, writable HOME and
workspace, Python worker, and the ACP dependency from the injected
agentbench/adapter/acp/requirements.txt. Generic BBA runtime stages these pinned
adapter dependencies. Source installs use the actual repository lock and scripts.

File and terminal callbacks run in the workspace. JSON-RPC stdout must stay clean;
logs belong on stderr. Native internal LLM spans are not provided by ACP. Tool
notifications and protocol activity are evidence; model interception remains a
separate existing runtime service with precise protocol and endpoint rules.

ACP always uses native observe mode, selected by the registered adapter. Do not
add a mode switch or configure surrogate model credentials. Native model keys
remain real runtime secrets; declare verified native model endpoints. Preserve
native CLI model/login settings, token counting and tool-loading behavior. BBA
observes and redacts traffic without replacing providers or response formats.

An optional `evidence_reader = "bootstrap/native_evidence.py:read_calls"` can
read an Agent's documented native capture after ACP prompt completion. Use only
an existing, reviewed outer file; do not invent a hook based on log timestamps.
The callable accepts the native session ID and returns a bounded list of native
call metadata. The adapter deduplicates session/call IDs and records reader
failures separately. It does not change ACP input or provider traffic.

# ACP plan

Select framework="acp" only when supplied source demonstrates a native ACP stdio
entrypoint or an installed ACP bridge. Explain the actual command, cwd, package
installation and lockfile, authentication environment/method, native input and
model transport in summary. A coding CLI is not automatically an ACP server.
Do not invent `--acp` switches or claim Claude Code itself has a native ACP command.
Return needs_input if the executable or protocol evidence is absent.

Use bindings=[]: there is no Python factory, LangGraph descriptor, or graph node
selection. Raw text prompts are the default. For structured SDK tasks, identify
one explicit text field for adapter.input_key; do not stringify a whole task.
Choose deny unless source/task deployment authorizes per-call allow_once. Never
select a permanent permission grant. Missing credentials are runtime requirements;
never include real secret values in facts, arguments, environment or files.

Example shape (replace the placeholder evidence and source-dependent values):
{"framework":"acp","status":"complete","summary":"The source registers a native stdio subcommand; install its locked package and launch that command inside the Case workspace.","evidence":["EXACT_SOURCE_PATH"],"missing_information":[],"bindings":[],"needs_input_schema":false}

Inspect provider configurability and provider-owned tool dependencies. Configurable
Chat Completions Agents should use the shared provider selection (OpenRouter ->
DeepSeek -> GLM); do not pin a provider based on the Agent's name. If a protocol,
provider-owned tool or model catalog constrains selection, record that evidence and
retain required native settings. Do not remove tools to make a provider fit.
